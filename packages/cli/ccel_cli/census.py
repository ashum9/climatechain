"""
Reproducible Sentinel-2 L2A scene census.

Replaces the single-page STAC query in stac_client.py, which fetched one page
of 100 items (newest first) and never followed pagination links.

Design:
  * Every results page is fetched by following STAC `next` links until none remain.
  * Every request/response is logged (method, URL, body, HTTP status, SHA-256 of the
    raw response bytes, numberMatched/numberReturned, item IDs).
  * Completeness is asserted, not assumed: a catalog result is COMPLETE only if
    pagination was exhausted AND (when the API reports numberMatched) the number of
    items received equals numberMatched.
  * Reprocessed duplicates of the same acquisition are grouped under one acquisition
    key = (datatake id without processing baseline, MGRS tile). The canonical item is
    the highest processing baseline; all variants are kept with their own cloud cover.
  * A second, independent catalog is queried and reconciled against the first.
  * There is no silent fallback. If a catalog cannot be queried, the census is marked
    INCOMPLETE and the reason is recorded.

Honest limitation: catalogs change over time (reprocessing campaigns, withdrawn items).
The query log records what was observed and when; `replay_census` re-runs the logged
query and reports differences.
"""

from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional, Tuple

import requests

CENSUS_SCHEMA_VERSION = "ccel-census/1.0"

CATALOGS: Dict[str, Dict[str, str]] = {
    "earth-search": {
        "searchUrl": "https://earth-search.aws.element84.com/v1/search",
        "collection": "sentinel-2-l2a",
        "operator": "Element 84 / AWS Open Data (Copernicus Sentinel-2 L2A COGs)",
    },
    "planetary-computer": {
        "searchUrl": "https://planetarycomputer.microsoft.com/api/stac/v1/search",
        "collection": "sentinel-2-l2a",
        "operator": "Microsoft Planetary Computer (Copernicus Sentinel-2 L2A)",
    },
}

DEDUP_RULE = (
    "Items are grouped by acquisition key = (s2:datatake_id with the trailing processing-baseline "
    "suffix removed, MGRS tile). Within a group the canonical item is the one with the highest "
    "s2:processing_baseline, then the latest s2:generation_time, then item id. All variants are retained."
)

MAX_PAGES_DEFAULT = 500

# A fetcher takes (method, url, json_body) and returns (status_code, raw_bytes).
Fetcher = Callable[[str, str, Optional[Dict[str, Any]]], Tuple[int, bytes]]


def _default_fetcher(method: str, url: str, body: Optional[Dict[str, Any]]) -> Tuple[int, bytes]:
    if method.upper() == "POST":
        resp = requests.post(url, json=body, timeout=60)
    else:
        resp = requests.get(url, timeout=60)
    return resp.status_code, resp.content


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


# --------------------------------------------------------------------------------------
# Pagination
# --------------------------------------------------------------------------------------

def fetch_all_pages(
    catalog_id: str,
    query_body: Dict[str, Any],
    fetcher: Optional[Fetcher] = None,
    max_pages: int = MAX_PAGES_DEFAULT,
) -> Dict[str, Any]:
    """
    Fetches every page of a STAC /search result by following `next` links.

    Returns a dict with: features, pages (request/response log), numberMatched (first page
    value or None), exhausted (bool), complete (bool), failureReason (str|None).
    """
    fetch = fetcher or _default_fetcher
    cat = CATALOGS[catalog_id]

    method, url, body = "POST", cat["searchUrl"], dict(query_body)
    features: List[Dict[str, Any]] = []
    pages: List[Dict[str, Any]] = []
    number_matched: Optional[int] = None
    exhausted = False
    failure: Optional[str] = None

    for page_index in range(max_pages):
        try:
            status, raw = fetch(method, url, body if method == "POST" else None)
        except Exception as exc:  # network error
            failure = f"request error on page {page_index}: {type(exc).__name__}: {exc}"
            break

        page_log: Dict[str, Any] = {
            "pageIndex": page_index,
            "requestMethod": method,
            "requestUrl": url,
            "requestBody": body if method == "POST" else None,
            "httpStatus": status,
            "responseSha256": hashlib.sha256(raw).hexdigest(),
            "responseBytes": len(raw),
        }

        if status != 200:
            page_log["itemIds"] = []
            pages.append(page_log)
            failure = f"HTTP {status} on page {page_index}"
            break

        try:
            data = json.loads(raw)
        except ValueError:
            pages.append(page_log)
            failure = f"invalid JSON on page {page_index}"
            break

        page_features = data.get("features", []) or []
        matched = data.get("numberMatched")
        if matched is None:
            matched = (data.get("context") or {}).get("matched")
        if page_index == 0:
            number_matched = matched

        page_log["numberMatched"] = matched
        page_log["numberReturned"] = data.get("numberReturned", len(page_features))
        page_log["itemIds"] = [f.get("id") for f in page_features]
        pages.append(page_log)
        features.extend(page_features)

        next_links = [l for l in data.get("links", []) or [] if l.get("rel") == "next"]
        if not next_links or not page_features:
            exhausted = True
            break

        nxt = next_links[0]
        next_method = (nxt.get("method") or "GET").upper()
        url = nxt.get("href", url)
        if next_method == "POST":
            next_body = nxt.get("body")
            if nxt.get("merge") and next_body is not None:
                merged = dict(body or {})
                merged.update(next_body)
                next_body = merged
            body = next_body if next_body is not None else body
            method = "POST"
        else:
            method, body = "GET", None
    else:
        failure = f"max_pages ({max_pages}) reached before pagination was exhausted"

    received = len(features)
    count_ok = number_matched is None or received == number_matched
    complete = exhausted and failure is None and count_ok
    if exhausted and not count_ok and failure is None:
        failure = f"received {received} items but API reported numberMatched={number_matched}"

    return {
        "catalog": catalog_id,
        "features": features,
        "pages": pages,
        "numberMatched": number_matched,
        "itemsReceived": received,
        "exhausted": exhausted,
        "complete": complete,
        "failureReason": failure,
    }


# --------------------------------------------------------------------------------------
# Normalisation & de-duplication
# --------------------------------------------------------------------------------------

_BASELINE_SUFFIX = re.compile(r"_N\d{2}\.\d{2}$")


def _tile_of(props: Dict[str, Any]) -> Optional[str]:
    tile = props.get("s2:mgrs_tile")
    if tile:
        return str(tile)
    code = props.get("grid:code")
    if code:
        return str(code).replace("MGRS-", "")
    if props.get("mgrs:utm_zone") is not None:
        return f"{props['mgrs:utm_zone']}{props.get('mgrs:latitude_band', '')}{props.get('mgrs:grid_square', '')}"
    return None


def _baseline_tuple(b: Optional[str]) -> Tuple[int, int]:
    try:
        major, minor = str(b).split(".")
        return int(major), int(minor)
    except Exception:
        return (-1, -1)


def _asset_href(assets: Dict[str, Any], *names: str) -> Optional[str]:
    for n in names:
        if n in assets and isinstance(assets[n], dict):
            return assets[n].get("href")
    return None


def normalize_item(feature: Dict[str, Any], catalog_id: str) -> Dict[str, Any]:
    props = feature.get("properties", {}) or {}
    datatake = props.get("s2:datatake_id")
    tile = _tile_of(props)
    datatake_base = _BASELINE_SUFFIX.sub("", datatake) if datatake else None
    sensing = None
    if datatake_base:
        # e.g. GS2A_20231230T044211_044503 -> 20231230T044211
        parts = datatake_base.split("_")
        if len(parts) >= 2:
            sensing = parts[1]
    acq_date = None
    if sensing and len(sensing) >= 8:
        acq_date = f"{sensing[0:4]}-{sensing[4:6]}-{sensing[6:8]}"
    elif props.get("datetime"):
        acq_date = str(props["datetime"])[:10]

    assets = feature.get("assets", {}) or {}
    geom = feature.get("geometry")
    geom_sha = hashlib.sha256(json.dumps(geom, sort_keys=True, separators=(",", ":")).encode()).hexdigest() if geom else None
    cloud = props.get("eo:cloud_cover")

    return {
        "catalog": catalog_id,
        "itemId": feature.get("id"),
        "acquisitionKey": f"{datatake_base}|{tile}" if datatake_base and tile else f"{acq_date}|{tile}",
        "acquisitionDate": acq_date,
        "sensingStart": sensing,
        "itemDatetime": props.get("datetime"),
        "mgrsTile": tile,
        "platform": props.get("platform"),
        "relativeOrbit": props.get("sat:relative_orbit"),
        "processingBaseline": props.get("s2:processing_baseline"),
        "generationTime": props.get("s2:generation_time"),
        "tileCloudCoverPct": round(float(cloud), 4) if cloud is not None else None,
        "tileNodataPct": props.get("s2:nodata_pixel_percentage"),
        "sclHref": _asset_href(assets, "scl", "SCL"),
        "visualHref": _asset_href(assets, "visual"),
        "geometrySha256": geom_sha,
    }


def dedupe_acquisitions(items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    groups: Dict[str, List[Dict[str, Any]]] = {}
    for it in items:
        groups.setdefault(it["acquisitionKey"], []).append(it)

    out = []
    for key, variants in groups.items():
        ranked = sorted(
            variants,
            key=lambda v: (_baseline_tuple(v["processingBaseline"]), v.get("generationTime") or "", v.get("itemId") or ""),
            reverse=True,
        )
        canonical = ranked[0]
        out.append({
            "acquisitionKey": key,
            "acquisitionDate": canonical["acquisitionDate"],
            "mgrsTile": canonical["mgrsTile"],
            "platform": canonical["platform"],
            "relativeOrbit": canonical["relativeOrbit"],
            "canonicalItemId": canonical["itemId"],
            "canonicalProcessingBaseline": canonical["processingBaseline"],
            "tileCloudCoverPct": canonical["tileCloudCoverPct"],
            "tileNodataPct": canonical["tileNodataPct"],
            "sclHref": canonical["sclHref"],
            "visualHref": canonical["visualHref"],
            "variants": [
                {
                    "itemId": v["itemId"],
                    "processingBaseline": v["processingBaseline"],
                    "tileCloudCoverPct": v["tileCloudCoverPct"],
                }
                for v in sorted(ranked, key=lambda v: v["itemId"] or "")
            ],
        })
    out.sort(key=lambda a: (a["acquisitionDate"] or "", a["mgrsTile"] or "", a["acquisitionKey"]))
    return out


# --------------------------------------------------------------------------------------
# Reconciliation
# --------------------------------------------------------------------------------------

def reconcile(primary: List[Dict[str, Any]], secondary: List[Dict[str, Any]], cloud_tolerance_pct: float = 1.0) -> Dict[str, Any]:
    a = {x["acquisitionKey"]: x for x in primary}
    b = {x["acquisitionKey"]: x for x in secondary}
    only_a = sorted(set(a) - set(b))
    only_b = sorted(set(b) - set(a))
    both = sorted(set(a) & set(b))

    cloud_disagreements = []
    for k in both:
        ca, cb = a[k]["tileCloudCoverPct"], b[k]["tileCloudCoverPct"]
        if ca is None or cb is None:
            continue
        if abs(ca - cb) > cloud_tolerance_pct:
            cloud_disagreements.append({
                "acquisitionKey": k,
                "primaryItemId": a[k]["canonicalItemId"],
                "primaryBaseline": a[k]["canonicalProcessingBaseline"],
                "primaryTileCloudPct": ca,
                "secondaryItemId": b[k]["canonicalItemId"],
                "secondaryBaseline": b[k]["canonicalProcessingBaseline"],
                "secondaryTileCloudPct": cb,
            })

    # Within-catalog reprocessing spread (same acquisition, different baselines, different cloud %)
    def spread(group):
        vals = [v["tileCloudCoverPct"] for v in group["variants"] if v["tileCloudCoverPct"] is not None]
        return (max(vals) - min(vals)) if len(vals) > 1 else 0.0

    reproc = [
        {"acquisitionKey": x["acquisitionKey"], "variants": x["variants"], "cloudSpreadPct": round(spread(x), 4)}
        for x in secondary + primary
        if len(x["variants"]) > 1 and spread(x) > cloud_tolerance_pct
    ]

    return {
        "matchedAcquisitions": len(both),
        "onlyInPrimary": only_a,
        "onlyInSecondary": only_b,
        "cloudToleranceTilePct": cloud_tolerance_pct,
        "tileCloudDisagreements": cloud_disagreements,
        "reprocessingCloudSpreads": sorted(reproc, key=lambda r: -r["cloudSpreadPct"]),
    }


# --------------------------------------------------------------------------------------
# Census build
# --------------------------------------------------------------------------------------

def make_query_definition(
    bbox: List[float],
    start_date: str,
    end_date: str,
    aoi_source: str,
    page_limit: int = 100,
    primary: str = "earth-search",
    secondary: Optional[str] = "planetary-computer",
) -> Dict[str, Any]:
    return {
        "schemaVersion": CENSUS_SCHEMA_VERSION,
        "collection": "sentinel-2-l2a",
        "aoi": {"type": "bbox", "bboxWgs84": list(bbox), "source": aoi_source},
        "datetime": f"{start_date}T00:00:00Z/{end_date}T23:59:59Z",
        "pageLimit": page_limit,
        "primaryCatalog": primary,
        "secondaryCatalog": secondary,
        "dedupRule": DEDUP_RULE,
    }


def _stac_body(qd: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "collections": [qd["collection"]],
        "bbox": qd["aoi"]["bboxWgs84"],
        "datetime": qd["datetime"],
        "limit": qd["pageLimit"],
    }


def run_census(query_definition: Dict[str, Any], fetcher: Optional[Fetcher] = None, max_pages: int = MAX_PAGES_DEFAULT) -> Dict[str, Any]:
    """
    Executes the census described by `query_definition`.

    Returns {"census": <committed census>, "queryLog": <committed query log>}.
    The census contains only normalised, deterministic content (no retrieval timestamps),
    so two runs against an unchanged catalog produce byte-identical census JSON.
    """
    body = _stac_body(query_definition)
    results: Dict[str, Dict[str, Any]] = {}
    for role in ("primaryCatalog", "secondaryCatalog"):
        cat = query_definition.get(role)
        if cat:
            results[cat] = fetch_all_pages(cat, body, fetcher=fetcher, max_pages=max_pages)

    deduped: Dict[str, List[Dict[str, Any]]] = {}
    catalog_summaries = []
    for cat, res in results.items():
        items = [normalize_item(f, cat) for f in res["features"]]
        deduped[cat] = dedupe_acquisitions(items)
        catalog_summaries.append({
            "catalog": cat,
            "searchUrl": CATALOGS[cat]["searchUrl"],
            "complete": res["complete"],
            "exhausted": res["exhausted"],
            "failureReason": res["failureReason"],
            "pagesFetched": len(res["pages"]),
            "numberMatched": res["numberMatched"],
            "itemsReceived": res["itemsReceived"],
            "uniqueAcquisitions": len(deduped[cat]),
            "reprocessedDuplicateItems": res["itemsReceived"] - len(deduped[cat]),
        })

    primary = query_definition["primaryCatalog"]
    secondary = query_definition.get("secondaryCatalog")
    recon = reconcile(deduped[primary], deduped[secondary]) if secondary and secondary in deduped else None

    primary_ok = results[primary]["complete"]
    secondary_ok = results[secondary]["complete"] if secondary else True
    if not primary_ok:
        status = "INCOMPLETE"
    elif not secondary_ok:
        status = "COMPLETE_PRIMARY_ONLY"
    elif recon and (recon["onlyInPrimary"] or recon["onlyInSecondary"]):
        status = "COMPLETE_WITH_CATALOG_DISCREPANCIES"
    else:
        status = "COMPLETE_AND_RECONCILED"

    acquisitions = deduped[primary]
    months: Dict[str, int] = {}
    tiles: Dict[str, int] = {}
    for a in acquisitions:
        m = (a["acquisitionDate"] or "")[:7]
        months[m] = months.get(m, 0) + 1
        tiles[a["mgrsTile"]] = tiles.get(a["mgrsTile"], 0) + 1
    dates = sorted({a["acquisitionDate"] for a in acquisitions if a["acquisitionDate"]})

    census = {
        "queryDefinition": query_definition,
        "censusStatus": status,
        "catalogs": catalog_summaries,
        "coverage": {
            "firstAcquisitionDate": dates[0] if dates else None,
            "lastAcquisitionDate": dates[-1] if dates else None,
            "distinctAcquisitionDates": len(dates),
            "acquisitionsPerMonth": dict(sorted(months.items())),
            "acquisitionsPerTile": dict(sorted(tiles.items())),
        },
        "reconciliation": recon,
        "cloudMetricNote": (
            "tileCloudCoverPct is eo:cloud_cover for the whole ~110 km MGRS tile, NOT cloud over the "
            "project polygons. Do not use it to judge scene suitability for the project area."
        ),
        "acquisitions": acquisitions,
    }

    query_log = {
        "schemaVersion": CENSUS_SCHEMA_VERSION,
        "retrievedAtUtc": _utc_now(),
        "queryDefinition": query_definition,
        "requests": {cat: res["pages"] for cat, res in results.items()},
    }
    return {"census": census, "queryLog": query_log}


def replay_census(stored_census: Dict[str, Any], fetcher: Optional[Fetcher] = None) -> Dict[str, Any]:
    """Re-runs the stored query definition and diffs acquisitions against the stored census."""
    fresh = run_census(stored_census["queryDefinition"], fetcher=fetcher)["census"]
    old = {a["acquisitionKey"]: a for a in stored_census["acquisitions"]}
    new = {a["acquisitionKey"]: a for a in fresh["acquisitions"]}
    changed = []
    for k in sorted(set(old) & set(new)):
        if (old[k]["canonicalItemId"], old[k]["tileCloudCoverPct"]) != (new[k]["canonicalItemId"], new[k]["tileCloudCoverPct"]):
            changed.append({"acquisitionKey": k, "stored": old[k]["canonicalItemId"], "fresh": new[k]["canonicalItemId"]})
    return {
        "identical": fresh == stored_census,
        "storedStatus": stored_census["censusStatus"],
        "freshStatus": fresh["censusStatus"],
        "added": sorted(set(new) - set(old)),
        "removed": sorted(set(old) - set(new)),
        "changed": changed,
    }
