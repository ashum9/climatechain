"""
VCS 1463 Boundary Parser & Licence-Safe Geometry Engine

Parses and validates the official boundary KML:
- Computes SHA-256 before parsing; raises BoundaryHashMismatchError if mismatch.
- Safely parses Placemarks (478) and Polygons (506).
- Computes WGS84 geodesic area (pyproj.Geod) and bounding box.
- Generates licence-safe boundary_summary.json with zero raw KML coordinate redistribution.
"""

import hashlib
import json
import os
import xml.etree.ElementTree as ET
from typing import Any, Dict, List, Optional, Tuple

import pyproj
from shapely.geometry import MultiPolygon, Polygon

from ccel_cli.config import (
    SUNDARBANS_VCS1463_BBOX_WGS84,
    VCS_1463_EXPECTED_KML_SHA256,
    VCS_1463_EXPECTED_PLACEMARKS,
    VCS_1463_EXPECTED_POLYGONS,
    VCS_1463_PROJECT_ID,
    VCS_1463_REGISTRY_URL,
    VCS_1463_STATED_AREA_HA,
)


class BoundaryError(Exception):
    pass


class BoundaryHashMismatchError(BoundaryError):
    pass


class BoundaryStructureMismatchError(BoundaryError):
    pass


def compute_file_sha256(filepath: str) -> str:
    h = hashlib.sha256()
    with open(filepath, "rb") as f:
        while chunk := f.read(65536):
            h.update(chunk)
    return h.hexdigest()


def parse_coordinates_text(coord_text: str) -> List[Tuple[float, float]]:
    coords = []
    for token in coord_text.strip().split():
        parts = token.strip().split(",")
        if len(parts) >= 2:
            try:
                lon = float(parts[0])
                lat = float(parts[1])
                coords.append((lon, lat))
            except ValueError:
                continue
    return coords


def verify_and_parse_kml_bytes(
    kml_bytes: bytes,
    expected_sha256: Optional[str] = VCS_1463_EXPECTED_KML_SHA256,
    strict_structure: bool = True,
    expected_placemarks: int = VCS_1463_EXPECTED_PLACEMARKS,
    expected_polygons: int = VCS_1463_EXPECTED_POLYGONS,
) -> Tuple[List[Polygon], Dict[str, Any]]:
    """
    Parses KML bytes, validates hashes and topology, and computes summary metrics.
    """
    actual_sha256 = hashlib.sha256(kml_bytes).hexdigest()
    if expected_sha256 and actual_sha256.lower() != expected_sha256.lower():
        raise BoundaryHashMismatchError(
            f"KML SHA-256 mismatch: expected {expected_sha256}, got {actual_sha256}"
        )

    # XML entity injection safety check
    if b"<!ENTITY" in kml_bytes or b"<!DOCTYPE" in kml_bytes:
        raise BoundaryError("DOCTYPE/ENTITY declarations are forbidden for XXE safety")

    root = ET.fromstring(kml_bytes)

    # Namespaces can vary in KML (http://www.opengis.net/kml/2.2 or none)
    ns = {"kml": "http://www.opengis.net/kml/2.2"}
    # Check if namespace is present
    has_ns = root.tag.startswith("{http://www.opengis.net/kml/2.2}")

    def find_all(element, tag_name):
        if has_ns:
            return element.findall(f".//{{{ns['kml']}}}{tag_name}")
        return element.findall(f".//{tag_name}")

    placemarks = find_all(root, "Placemark")
    placemark_count = len(placemarks)

    polygon_elements = find_all(root, "Polygon")
    polygon_count = len(polygon_elements)

    if strict_structure:
        if placemark_count != expected_placemarks or polygon_count != expected_polygons:
            raise BoundaryStructureMismatchError(
                f"KML structure mismatch: expected {expected_placemarks} placemarks / "
                f"{expected_polygons} polygons, got {placemark_count} / {polygon_count}"
            )

    geod = pyproj.Geod(ellps="WGS84")
    polygons: List[Polygon] = []
    polygon_hashes: List[str] = []
    total_area_m2 = 0.0

    min_lon, min_lat = 180.0, 90.0
    max_lon, max_lat = -180.0, -90.0

    for poly_elem in polygon_elements:
        outer_ring_elem = find_all(poly_elem, "outerBoundaryIs")
        if not outer_ring_elem:
            continue
        coord_elem = find_all(outer_ring_elem[0], "coordinates")
        if not coord_elem or not coord_elem[0].text:
            continue

        shell_coords = parse_coordinates_text(coord_elem[0].text)
        if len(shell_coords) < 3:
            continue

        # Check coordinate bounds
        for lon, lat in shell_coords:
            min_lon = min(min_lon, lon)
            min_lat = min(min_lat, lat)
            max_lon = max(max_lon, lon)
            max_lat = max(max_lat, lat)

        # Holes / inner boundaries
        holes = []
        inner_rings = find_all(poly_elem, "innerBoundaryIs")
        for inner in inner_rings:
            inner_coord_elem = find_all(inner, "coordinates")
            if inner_coord_elem and inner_coord_elem[0].text:
                hole_coords = parse_coordinates_text(inner_coord_elem[0].text)
                if len(hole_coords) >= 3:
                    holes.append(hole_coords)

        p = Polygon(shell_coords, holes)
        if not p.is_valid:
            p = p.buffer(0)

        polygons.append(p)
        poly_wkb = p.wkb
        poly_hash = hashlib.sha256(poly_wkb).hexdigest()
        polygon_hashes.append(poly_hash)

        # Geodesic area
        area_m2, _ = geod.geometry_area_perimeter(p)
        total_area_m2 += abs(area_m2)

    total_geodesic_ha = round(total_area_m2 / 10000.0, 2)
    overall_bbox = [round(min_lon, 6), round(min_lat, 6), round(max_lon, 6), round(max_lat, 6)]

    # Polygon commitments hash
    all_poly_hashes_str = "\n".join(sorted(polygon_hashes))
    polygon_commitments_hash = hashlib.sha256(all_poly_hashes_str.encode("utf-8")).hexdigest()

    summary = {
        "projectId": VCS_1463_PROJECT_ID,
        "kmlSha256": actual_sha256,
        "placemarkCount": placemark_count,
        "polygonCount": polygon_count,
        "statedAreaHa": VCS_1463_STATED_AREA_HA,
        "computedGeodesicAreaHa": total_geodesic_ha,
        "overallBboxWgs84": overall_bbox,
        "polygonCommitmentsHash": polygon_commitments_hash,
        "redistributionStatus": "SOURCE_LINK_ONLY_UNRESOLVED_LICENCE",
        "redistributionNotice": (
            f"Official Verra VCS 1463 boundary KML is not redistributed due to unresolved reuse licensing. "
            f"Download directly from {VCS_1463_REGISTRY_URL} and verify sha256 == {actual_sha256}."
        ),
    }

    return polygons, summary


def generate_boundary_summary_from_file(kml_path: str, out_path: Optional[str] = None) -> Dict[str, Any]:
    with open(kml_path, "rb") as f:
        kml_bytes = f.read()

    _, summary = verify_and_parse_kml_bytes(kml_bytes)

    if out_path:
        os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(summary, f, indent=2)

    return summary


def get_default_boundary_summary() -> Dict[str, Any]:
    """
    Returns the pinned licence-safe summary commitment for VCS 1463.
    """
    return {
        "projectId": VCS_1463_PROJECT_ID,
        "kmlSha256": VCS_1463_EXPECTED_KML_SHA256,
        "placemarkCount": VCS_1463_EXPECTED_PLACEMARKS,
        "polygonCount": VCS_1463_EXPECTED_POLYGONS,
        "statedAreaHa": VCS_1463_STATED_AREA_HA,
        "overallBboxWgs84": SUNDARBANS_VCS1463_BBOX_WGS84,
        "redistributionStatus": "SOURCE_LINK_ONLY_UNRESOLVED_LICENCE",
        "redistributionNotice": (
            f"Official Verra VCS 1463 boundary KML is not redistributed due to unresolved reuse licensing. "
            f"Download directly from {VCS_1463_REGISTRY_URL} and verify sha256 == {VCS_1463_EXPECTED_KML_SHA256}."
        ),
    }
