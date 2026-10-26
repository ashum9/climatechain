"""
Scene Selection Rule Evaluator.

Non-accusatory evaluation of submitted satellite scenes against a declared selection rule
and the complete multi-catalog scene census.

Outcomes:
  * CONSISTENT_WITH_RULE: The selected scene satisfies the pre-declared rule criteria.
  * RATIONALE_REQUESTED: Alternative candidate scenes with higher usable area existed
    in the window and were passed over. A selection rationale is requested.
  * RULE_NOT_DECLARED: No formal selection rule was committed; alternatives are presented
    for informational comparison.
  * CENSUS_INCOMPLETE: The satellite census could not be verified completely; no reliable
    comparison is possible.
"""

from typing import Any, Dict, List, Optional


def evaluate_scene_selection(
    submitted_scene_id: str,
    submitted_datetime: str,
    submitted_usable_pct: float,
    selection_rule: Optional[Dict[str, Any]],
    census_acquisitions: List[Dict[str, Any]],
    aoi_metrics_map: Optional[Dict[str, Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """
    Evaluates the submitted scene against the census and selection rule.
    """
    if not census_acquisitions:
        return {
            "outcome": "CENSUS_INCOMPLETE",
            "message": "Candidate scene census is empty or incomplete; selection consistency cannot be assessed.",
            "alternatives": [],
        }

    if not selection_rule:
        return {
            "outcome": "RULE_NOT_DECLARED",
            "message": "No selection rule was declared. Candidate scenes are listed for independent verification.",
            "alternatives": [],
        }

    target_months = selection_rule.get("targetSeasonMonths", ["11", "12", "01", "02"])
    min_usable_pct = float(selection_rule.get("minUsablePct", 80.0))

    # Identify candidate scenes in the target season
    season_candidates = []
    for acq in census_acquisitions:
        dt = acq.get("acquisitionDate") or ""
        month = dt[5:7] if len(dt) >= 7 else ""
        if target_months and month not in target_months:
            continue

        item_id = acq.get("canonicalItemId") or acq.get("id")
        tile_cloud = acq.get("tileCloudCoverPct", 100.0)

        # Look up true AoI usable % if available, else derive from tile cloud
        usable = 100.0 - float(tile_cloud)
        if aoi_metrics_map and item_id in aoi_metrics_map:
            m = aoi_metrics_map[item_id]
            if m.get("aoiUsablePct") is not None:
                usable = float(m["aoiUsablePct"])

        season_candidates.append({
            "itemId": item_id,
            "acquisitionDate": dt,
            "mgrsTile": acq.get("mgrsTile"),
            "usablePct": round(usable, 2),
            "tileCloudCoverPct": tile_cloud,
            "sclHref": acq.get("sclHref"),
        })

    # Sort candidates by usable % descending, then by date
    season_candidates.sort(key=lambda c: (-c["usablePct"], c["acquisitionDate"]))

    # Look for better alternatives
    better_alternatives = [
        c for c in season_candidates
        if c["usablePct"] > submitted_usable_pct and c["usablePct"] >= min_usable_pct
        and c["itemId"] != submitted_scene_id
    ]

    is_consistent = (
        submitted_usable_pct >= min_usable_pct
        and len(better_alternatives) == 0
    )

    if is_consistent:
        outcome = "CONSISTENT_WITH_RULE"
        message = (
            f"Submitted scene {submitted_scene_id} satisfies the selection rule "
            f"(usable area {submitted_usable_pct:.1f}% >= {min_usable_pct:.1f}% threshold "
            f"with no clearer candidate scenes passed over in target season)."
        )
    else:
        outcome = "RATIONALE_REQUESTED"
        message = (
            f"Submitted scene {submitted_scene_id} has {submitted_usable_pct:.1f}% usable area. "
            f"{len(better_alternatives)} candidate scene(s) with higher usable area (>= {min_usable_pct:.1f}%) "
            f"were identified in the declared monitoring window. A selection rationale is requested."
        )

    return {
        "outcome": outcome,
        "message": message,
        "submittedSceneId": submitted_scene_id,
        "submittedUsablePct": submitted_usable_pct,
        "ruleMinUsablePct": min_usable_pct,
        "seasonCandidatesCount": len(season_candidates),
        "betterAlternativesCount": len(better_alternatives),
        "betterAlternatives": better_alternatives[:10],
    }
