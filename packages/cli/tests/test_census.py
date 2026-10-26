import json
import pytest
from ccel_cli.census import (
    fetch_all_pages,
    dedupe_acquisitions,
    normalize_item,
    reconcile,
    replay_census,
    run_census,
    make_query_definition,
)


def test_pagination_follows_next_links_completely():
    # Mock a 3-page STAC API with 15 total items (5 per page)
    pages_data = [
        {
            "numberMatched": 15,
            "numberReturned": 5,
            "features": [{"id": f"item_{i}", "properties": {"datetime": f"2023-01-{i:02d}T00:00:00Z", "s2:mgrs_tile": "45QYE"}} for i in range(1, 6)],
            "links": [{"rel": "next", "method": "POST", "href": "https://api.test/search", "body": {"page": 2}}],
        },
        {
            "numberMatched": 15,
            "numberReturned": 5,
            "features": [{"id": f"item_{i}", "properties": {"datetime": f"2023-01-{i:02d}T00:00:00Z", "s2:mgrs_tile": "45QYE"}} for i in range(6, 11)],
            "links": [{"rel": "next", "method": "POST", "href": "https://api.test/search", "body": {"page": 3}}],
        },
        {
            "numberMatched": 15,
            "numberReturned": 5,
            "features": [{"id": f"item_{i}", "properties": {"datetime": f"2023-01-{i:02d}T00:00:00Z", "s2:mgrs_tile": "45QYE"}} for i in range(11, 16)],
            "links": [],
        },
    ]

    call_count = 0

    def mock_fetcher(method, url, body):
        nonlocal call_count
        idx = call_count
        call_count += 1
        return 200, json.dumps(pages_data[idx]).encode("utf-8")

    res = fetch_all_pages("earth-search", {"limit": 5}, fetcher=mock_fetcher)
    assert res["complete"] is True
    assert res["exhausted"] is True
    assert res["itemsReceived"] == 15
    assert len(res["pages"]) == 3
    assert [p["pageIndex"] for p in res["pages"]] == [0, 1, 2]
    assert res["features"][0]["id"] == "item_1"
    assert res["features"][-1]["id"] == "item_15"


def test_pagination_flags_premature_termination():
    # API reports numberMatched=50, but gives only 1 page with 10 items and no next link
    broken_page = {
        "numberMatched": 50,
        "numberReturned": 10,
        "features": [{"id": f"item_{i}", "properties": {}} for i in range(10)],
        "links": [],
    }

    def mock_fetcher(method, url, body):
        return 200, json.dumps(broken_page).encode("utf-8")

    res = fetch_all_pages("earth-search", {"limit": 10}, fetcher=mock_fetcher)
    assert res["complete"] is False
    assert "received 10 items but API reported numberMatched=50" in res["failureReason"]


def test_deduplication_prefers_higher_processing_baseline():
    raw_features = [
        {
            "id": "S2A_MSIL2A_20231212_N05.09_T45QYE",
            "properties": {
                "s2:datatake_id": "GS2A_20231212T043149_044246_N05.09",
                "s2:mgrs_tile": "45QYE",
                "s2:processing_baseline": "05.09",
                "eo:cloud_cover": 3.23,
                "datetime": "2023-12-12T04:42:00Z",
            },
        },
        {
            "id": "S2A_MSIL2A_20231212_N05.10_T45QYE",
            "properties": {
                "s2:datatake_id": "GS2A_20231212T043149_044246_N05.10",
                "s2:mgrs_tile": "45QYE",
                "s2:processing_baseline": "05.10",
                "eo:cloud_cover": 0.52,
                "datetime": "2023-12-12T04:42:00Z",
            },
        },
    ]

    items = [normalize_item(f, "planetary-computer") for f in raw_features]
    deduped = dedupe_acquisitions(items)

    assert len(deduped) == 1
    acq = deduped[0]
    assert acq["canonicalItemId"] == "S2A_MSIL2A_20231212_N05.10_T45QYE"
    assert acq["canonicalProcessingBaseline"] == "05.10"
    assert len(acq["variants"]) == 2


def test_reconciliation_identifies_matching_and_divergent_catalogs():
    primary = [
        {"acquisitionKey": "A|45QXE", "canonicalItemId": "P1", "canonicalProcessingBaseline": "05.10", "tileCloudCoverPct": 5.0, "variants": []},
        {"acquisitionKey": "B|45QYE", "canonicalItemId": "P2", "canonicalProcessingBaseline": "05.10", "tileCloudCoverPct": 10.0, "variants": []},
    ]
    secondary = [
        {"acquisitionKey": "A|45QXE", "canonicalItemId": "S1", "canonicalProcessingBaseline": "05.10", "tileCloudCoverPct": 5.1, "variants": []},
        {"acquisitionKey": "B|45QYE", "canonicalItemId": "S2", "canonicalProcessingBaseline": "05.09", "tileCloudCoverPct": 14.5, "variants": []},
    ]

    recon = reconcile(primary, secondary, cloud_tolerance_pct=1.0)
    assert recon["matchedAcquisitions"] == 2
    assert recon["onlyInPrimary"] == []
    assert recon["onlyInSecondary"] == []
    # Key B has cloud divergence (10.0 vs 14.5 > 1.0)
    assert len(recon["tileCloudDisagreements"]) == 1
    assert recon["tileCloudDisagreements"][0]["acquisitionKey"] == "B|45QYE"
