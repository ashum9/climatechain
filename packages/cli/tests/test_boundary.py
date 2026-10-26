import hashlib
import json
import os
import sys
import pytest

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../")))

from ccel_cli.boundary import (
    BoundaryError,
    BoundaryHashMismatchError,
    BoundaryStructureMismatchError,
    get_default_boundary_summary,
    verify_and_parse_kml_bytes,
)
from ccel_cli.config import (
    VCS_1463_EXPECTED_KML_SHA256,
    VCS_1463_EXPECTED_PLACEMARKS,
    VCS_1463_EXPECTED_POLYGONS,
)


def create_synthetic_kml(num_placemarks: int = 1, coords_str: str = "88.7,21.9 88.8,21.9 88.8,22.0 88.7,22.0 88.7,21.9") -> bytes:
    placemark_xml = ""
    for i in range(num_placemarks):
        placemark_xml += f"""
        <Placemark>
          <name>Plot {i+1}</name>
          <Polygon>
            <outerBoundaryIs>
              <LinearRing>
                <coordinates>{coords_str}</coordinates>
              </LinearRing>
            </outerBoundaryIs>
          </Polygon>
        </Placemark>
        """
    return f"""<?xml version="1.0" encoding="UTF-8"?>
    <kml xmlns="http://www.opengis.net/kml/2.2">
      <Document>
        {placemark_xml}
      </Document>
    </kml>""".encode("utf-8")


def test_synthetic_kml_parsing():
    raw = create_synthetic_kml(num_placemarks=2)
    expected_hash = hashlib.sha256(raw).hexdigest()

    polygons, summary = verify_and_parse_kml_bytes(
        raw,
        expected_sha256=expected_hash,
        strict_structure=False
    )
    assert len(polygons) == 2
    assert summary["placemarkCount"] == 2
    assert summary["polygonCount"] == 2
    assert summary["overallBboxWgs84"] == [88.7, 21.9, 88.8, 22.0]
    assert summary["computedGeodesicAreaHa"] > 0
    assert "coordinates" not in summary  # Licence safe!


def test_kml_hash_mismatch():
    raw = create_synthetic_kml(num_placemarks=1)
    wrong_hash = "0000000000000000000000000000000000000000000000000000000000000000"
    with pytest.raises(BoundaryHashMismatchError):
        verify_and_parse_kml_bytes(raw, expected_sha256=wrong_hash)


def test_strict_structure_mismatch():
    raw = create_synthetic_kml(num_placemarks=5)  # Not 478
    raw_hash = hashlib.sha256(raw).hexdigest()
    # If we pass VCS_1463_EXPECTED_KML_SHA256, it will fail hash check first, but if we test structure:
    with pytest.raises(BoundaryStructureMismatchError):
        verify_and_parse_kml_bytes(raw, expected_sha256=raw_hash, strict_structure=True)


def test_xxe_entity_injection_rejected():
    malicious_xml = b"""<?xml version="1.0"?>
    <!DOCTYPE foo [<!ENTITY xxe SYSTEM "file:///etc/passwd">]>
    <kml xmlns="http://www.opengis.net/kml/2.2">
      <Document>&xxe;</Document>
    </kml>"""
    with pytest.raises(BoundaryError) as exc_info:
        verify_and_parse_kml_bytes(malicious_xml, expected_sha256=None, strict_structure=False)
    assert "XXE safety" in str(exc_info.value)


def test_default_summary_licence_safe():
    summary = get_default_boundary_summary()
    assert summary["projectId"] == "VCS-1463"
    assert summary["kmlSha256"] == VCS_1463_EXPECTED_KML_SHA256
    assert summary["placemarkCount"] == VCS_1463_EXPECTED_PLACEMARKS
    assert summary["polygonCount"] == VCS_1463_EXPECTED_POLYGONS
    assert summary["statedAreaHa"] == 4675.0
    assert summary["redistributionStatus"] == "SOURCE_LINK_ONLY_UNRESOLVED_LICENCE"
    # Ensure no raw coordinates are in the summary
    json_str = json.dumps(summary)
    assert "coordinates" not in json_str
    assert "LinearRing" not in json_str
