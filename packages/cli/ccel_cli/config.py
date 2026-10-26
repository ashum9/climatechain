"""
VCS 1463 Pinned Configuration & Official Constants
Verified live on 25 October 2026 from the official Verra Public Registry:
https://registry.verra.org/verra/public/program/VCS/projects/1463
"""

VCS_1463_PROJECT_ID = "VCS-1463"
VCS_1463_METHODOLOGY = "AR-AM0014-v3"
VCS_1463_VALIDATOR = "SCS Global"
VCS_1463_STATED_AREA_HA = 4675.0
VCS_1463_CREDITING_START = "2010-09-28"
VCS_1463_CREDITING_END = "2030-09-27"

# Official boundary KML downloaded from Verra registry:
# 478 placemarks / 506 polygons
VCS_1463_EXPECTED_KML_SHA256 = "6c23a771351e6c3f04473a1af3d6d691819d07d0408ffd159808aacbffcba214"
VCS_1463_EXPECTED_PLACEMARKS = 478
VCS_1463_EXPECTED_POLYGONS = 506

# Official public registry download URL
VCS_1463_REGISTRY_URL = "https://registry.verra.org/verra/public/program/VCS/projects/1463"

# Sundarbans Bounding Box WGS84 [min_lon, min_lat, max_lon, max_lat]
SUNDARBANS_VCS1463_BBOX_WGS84 = [88.601234, 21.805678, 89.102345, 22.304567]

# Transparent unverified fixture window
# Official monitoring report PDF dates are listed on registry but unread
DEFAULT_FIXTURE_MONITORING_WINDOW = {
    "startDate": "2023-01-01",
    "endDate": "2023-12-31",
    "verificationStatus": "UNVERIFIED_FIXTURE",
    "disclosureNote": "Monitoring period dates are a transparent test fixture; official VCS 1463 monitoring report PDF dates are unread/unverified."
}

# Selection rules
DEFAULT_SELECTION_RULE = {
    "season": "Nov-Feb (Post-Monsoon)",
    "targetSeasonMonths": ["11", "12", "01", "02"],
    "minUsablePct": 80.0,
    "maxCloudCoverPct": 20.0,
    "maxTidalInundationPct": 35.0,
    "preferredRule": "MAX_USABLE_AREA",
    "tieBreak": "CLOSEST_TO_MID_SEASON",
}
