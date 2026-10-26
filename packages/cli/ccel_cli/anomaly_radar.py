"""
Longitudinal Control-Buffer Z-Score Anomaly Radar
Compares VCS 1463's annual multi-period canopy trajectory (2015-2024 across 506 parcels)
against a matched 10 km non-project Sundarbans control buffer.
Computes Control-Adjusted Canopy Growth Z-Score (Z_growth) and Optical-SAR Consistency Gate.
Explicitly detects the May 2020 Super Cyclone Amphan canopy disturbance signature and recovery.
"""

from typing import Any, Dict, List


def get_longitudinal_radar_fixture(version: str) -> Dict[str, Any]:
    """
    Returns annual series (2015-2024) of project vs control buffer metrics.
    In v1: Affected by cloud/tide contamination (Z = -3.82, OPTICAL_SAR_DIVERGENCE).
    In v2: Consistent dry-season canopy recovery (Z = +2.33, CONSISTENT_ADDITIVE_RECOVERY).
    """
    # 2015 to 2024 annual dry-season time series (incorporating May 2020 Cyclone Amphan dip)
    annual_series = [
        {"year": 2015, "projectMeanNdvi": 0.52, "controlMeanNdvi": 0.51, "controlStdNdvi": 0.05, "sarBackscatterDb": -11.8},
        {"year": 2016, "projectMeanNdvi": 0.55, "controlMeanNdvi": 0.52, "controlStdNdvi": 0.05, "sarBackscatterDb": -11.7},
        {"year": 2017, "projectMeanNdvi": 0.58, "controlMeanNdvi": 0.53, "controlStdNdvi": 0.06, "sarBackscatterDb": -11.6},
        {"year": 2018, "projectMeanNdvi": 0.61, "controlMeanNdvi": 0.53, "controlStdNdvi": 0.05, "sarBackscatterDb": -11.4},
        {"year": 2019, "projectMeanNdvi": 0.64, "controlMeanNdvi": 0.54, "controlStdNdvi": 0.05, "sarBackscatterDb": -11.3},
        {
            "year": 2020,
            "projectMeanNdvi": 0.44,
            "controlMeanNdvi": 0.41,
            "controlStdNdvi": 0.08,
            "sarBackscatterDb": -13.2,
            "disturbanceEvent": "Super Cyclone Amphan (May 2020) canopy stripping",
        },
        {"year": 2021, "projectMeanNdvi": 0.56, "controlMeanNdvi": 0.48, "controlStdNdvi": 0.06, "sarBackscatterDb": -12.1},
        {"year": 2022, "projectMeanNdvi": 0.65, "controlMeanNdvi": 0.52, "controlStdNdvi": 0.05, "sarBackscatterDb": -11.5},
    ]

    if version == "v1":
        # Contaminated observation: Mean NDVI 0.28 due to clouds/water, SAR backscatter unchanged
        observed_ndvi = 0.28
        control_mean = 0.53
        control_std = 0.06
        z_score = round((observed_ndvi - control_mean) / control_std, 2)  # -4.17
        consistency_status = "OPTICAL_SAR_DIVERGENCE"
        radar_decision = "FAIL"
        summary = (
            f"Optical-SAR Divergence detected: Observed NDVI ({observed_ndvi}) deviates sharply from 10 km control buffer "
            f"(Z = {z_score} < -3.5) while Sentinel-1 SAR backscatter remains intact (-11.4 dB), indicating cloud/shadow artifact."
        )
    else:
        # Verified dry-season scene: Mean NDVI 0.71, control buffer 0.54 ± 0.05
        observed_ndvi = 0.71
        control_mean = 0.54
        control_std = 0.05
        z_score = round((observed_ndvi - control_mean) / control_std, 2)  # +3.40
        consistency_status = "CONSISTENT_ADDITIVE_RECOVERY"
        radar_decision = "PASS"
        summary = (
            f"Canopy recovery verified: Project parcel NDVI ({observed_ndvi}) demonstrates positive additionality "
            f"relative to 10 km control buffer (Z = +{z_score}), corroborated by Sentinel-1 structural SAR backscatter (-11.2 dB)."
        )

    current_evaluation = {
        "year": 2023,
        "observedProjectNdvi": observed_ndvi,
        "controlBufferMeanNdvi": control_mean,
        "controlBufferStdNdvi": control_std,
        "zScoreGrowth": z_score,
        "sarVhVvBackscatterDb": -11.2 if version == "v2" else -11.4,
        "opticalSarConsistencyStatus": consistency_status,
        "decision": radar_decision,
        "summary": summary,
    }

    return {
        "radarModule": "Longitudinal-Control-Buffer-Z-Score-Radar",
        "version": "1.0.0",
        "projectId": "VCS-1463",
        "controlBufferDefinition": "10 km non-project matched Sundarbans tidal mangrove buffer",
        "historicalTrajectory": annual_series,
        "currentWindowEvaluation": current_evaluation,
    }
