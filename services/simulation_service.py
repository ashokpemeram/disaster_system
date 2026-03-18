from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timedelta
import logging
import random
from typing import Any

from pymongo import ReturnDocument

from db import area_collection, simulation_collection
from services.area_service import (
    DEFAULT_CONTROLLABLE_RADIUS_M,
    DEFAULT_GREEN_RADIUS_M,
    DEFAULT_RED_RADIUS_M,
    DEFAULT_WARNING_RADIUS_M,
    find_matching_area,
    get_area_by_id,
    match_or_create_area,
    parse_location_coordinates,
)

logger = logging.getLogger(__name__)

_SIMULATION_ID_CHARS = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"

_DEFAULT_THRESHOLD_PROFILE = {
    "wind_kph": {"medium": 35.0, "high": 60.0},
    "precip_mm": {"medium": 3.0, "high": 7.0},
    "temperature_c": {
        "high_medium": 32.0,
        "low_medium": 8.0,
        "high_high": 38.0,
        "low_high": 2.0,
    },
    "visibility_km": {"medium": 8.0, "high": 3.0},
    "uv_index": {"medium": 5.0, "high": 7.0},
}

_FORCED_THRESHOLD_OVERRIDES = {
    "low": {},
    "medium": {
        "wind_kph": {"medium": 0.1},
        "precip_mm": {"medium": 0.1},
        "temperature_c": {"high_medium": -100.0},
        "uv_index": {"medium": 0.0},
    },
    "high": {
        "wind_kph": {"medium": 0.1, "high": 0.2},
        "precip_mm": {"medium": 0.1, "high": 0.2},
        "temperature_c": {"high_medium": -100.0, "high_high": -99.0},
        "uv_index": {"medium": 0.0, "high": 0.1},
    },
}


def default_threshold_profile() -> dict[str, Any]:
    return deepcopy(_DEFAULT_THRESHOLD_PROFILE)


def merge_threshold_profile(
    base_profile: dict[str, Any],
    overrides: dict[str, Any] | None,
) -> dict[str, Any]:
    merged = deepcopy(base_profile)
    if not overrides:
        return merged

    for key, value in overrides.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = merge_threshold_profile(merged[key], value)
        else:
            merged[key] = value
    return merged


def build_forced_threshold_profile(
    severity: str,
    custom_threshold_profile: dict[str, Any] | None = None,
) -> dict[str, Any]:
    normalized_severity = (severity or "medium").lower()
    base = merge_threshold_profile(
        default_threshold_profile(),
        _FORCED_THRESHOLD_OVERRIDES.get(normalized_severity, {}),
    )
    return merge_threshold_profile(base, custom_threshold_profile)


def build_demo_area_profile(radius_m: float, severity: str) -> dict[str, float]:
    effective_radius = max(radius_m or 0.0, DEFAULT_WARNING_RADIUS_M)
    normalized_severity = (severity or "medium").lower()

    if normalized_severity == "high":
        red_radius = max(effective_radius, DEFAULT_RED_RADIUS_M)
        warning_radius = max(red_radius + 250.0, effective_radius * 1.35)
        green_radius = max(warning_radius + 200.0, effective_radius * 1.65)
        controllable_radius = max(green_radius + 300.0, effective_radius * 2.0)
    else:
        red_radius = max(DEFAULT_RED_RADIUS_M, effective_radius * 0.55)
        warning_radius = max(red_radius + 250.0, effective_radius)
        green_radius = max(warning_radius + 200.0, effective_radius * 1.25)
        controllable_radius = max(green_radius + 300.0, effective_radius * 1.6)

    return {
        "redRadiusM": red_radius,
        "warningRadiusM": warning_radius,
        "greenRadiusM": green_radius,
        "controllableRadiusM": max(controllable_radius, DEFAULT_CONTROLLABLE_RADIUS_M),
    }


def build_area_profile_snapshot(area: dict[str, Any]) -> dict[str, float]:
    return {
        "redRadiusM": float(area.get("redRadiusM", DEFAULT_RED_RADIUS_M)),
        "warningRadiusM": float(area.get("warningRadiusM", DEFAULT_WARNING_RADIUS_M)),
        "greenRadiusM": float(area.get("greenRadiusM", DEFAULT_GREEN_RADIUS_M)),
        "controllableRadiusM": float(
            area.get("controllableRadiusM", DEFAULT_CONTROLLABLE_RADIUS_M)
        ),
    }


def generate_simulation_id(now: datetime | None = None) -> str:
    stamp = (now or datetime.utcnow()).strftime("%Y%m%d%H%M%S")
    suffix = "".join(random.choice(_SIMULATION_ID_CHARS) for _ in range(4))
    return f"SIM-{stamp}-{suffix}"


def _parse_iso_datetime(value: Any) -> datetime | None:
    if not value:
        return None
    if isinstance(value, datetime):
        return value
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value)
        except ValueError:
            return None
    return None


def _restore_area_profile(area_id: str, original_area_profile: dict[str, Any] | None):
    if not original_area_profile:
        return get_area_by_id(area_id)

    area_collection.find_one_and_update(
        {"id": area_id},
        {"$set": original_area_profile},
        return_document=ReturnDocument.AFTER,
    )
    return get_area_by_id(area_id)


def _deactivate_session(
    session: dict[str, Any],
    *,
    stop_reason: str,
) -> tuple[dict[str, Any], dict[str, Any] | None]:
    now = datetime.utcnow().isoformat()
    area = _restore_area_profile(session["areaId"], session.get("originalAreaProfile"))
    updated_session = simulation_collection.find_one_and_update(
        {"id": session["id"]},
        {
            "$set": {
                "isActive": False,
                "stoppedAt": now,
                "stopReason": stop_reason,
            }
        },
        return_document=ReturnDocument.AFTER,
    )
    logger.info(
        "Simulation %s deactivated for area %s (%s).",
        session["id"],
        session["areaId"],
        stop_reason,
    )
    return updated_session or session, area


def _find_active_session_by_area(area_id: str) -> dict[str, Any] | None:
    return simulation_collection.find_one(
        {"areaId": area_id, "isActive": True},
        sort=[("startedAt", -1)],
    )


def stop_simulation(
    *,
    simulation_id: str | None = None,
    area_id: str | None = None,
    stop_reason: str = "manual_stop",
) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    session = None
    if simulation_id:
        session = simulation_collection.find_one({"id": simulation_id, "isActive": True})
    if session is None and area_id:
        session = _find_active_session_by_area(area_id)
    if session is None:
        return None, None
    return _deactivate_session(session, stop_reason=stop_reason)


def _expire_session_if_needed(session: dict[str, Any] | None) -> dict[str, Any] | None:
    if session is None:
        return None

    ends_at = _parse_iso_datetime(session.get("endsAt"))
    if ends_at is None or datetime.utcnow() < ends_at:
        return session

    logger.info("Simulation %s expired for area %s.", session["id"], session["areaId"])
    stop_simulation(simulation_id=session["id"], stop_reason="expired")
    return None


def get_active_simulation(
    *,
    area_id: str | None = None,
    latitude: float | None = None,
    longitude: float | None = None,
    location: str | None = None,
) -> dict[str, Any] | None:
    resolved_area_id = area_id
    if resolved_area_id is None and latitude is not None and longitude is not None:
        matched_area, _inside, _distance = find_matching_area(latitude, longitude)
        if matched_area is not None:
            resolved_area_id = matched_area["id"]

    if resolved_area_id is None and location:
        lat, lon = parse_location_coordinates(location)
        if lat is not None and lon is not None:
            matched_area, _inside, _distance = find_matching_area(lat, lon)
            if matched_area is not None:
                resolved_area_id = matched_area["id"]

    if resolved_area_id is None:
        return None

    session = _find_active_session_by_area(resolved_area_id)
    return _expire_session_if_needed(session)


def resolve_weather_threshold_profile(
    *,
    area_id: str | None = None,
    location: str | None = None,
) -> tuple[dict[str, Any], dict[str, Any] | None]:
    session = get_active_simulation(area_id=area_id, location=location)
    if session is None:
        return default_threshold_profile(), None

    profile = session.get("thresholdProfile")
    if isinstance(profile, dict):
        return merge_threshold_profile(default_threshold_profile(), profile), session
    return default_threshold_profile(), session


def start_simulation(
    *,
    area_id: str | None = None,
    latitude: float | None = None,
    longitude: float | None = None,
    radius_m: float | None = None,
    disaster_type: str,
    severity: str,
    duration_seconds: int | None = None,
    custom_threshold_profile: dict[str, Any] | None = None,
    total_citizens: int | None = None,
    interval_seconds: int | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    area = get_area_by_id(area_id) if area_id else None
    if area_id and area is None:
        raise ValueError("Disaster area not found.")

    if area is None:
        if latitude is None or longitude is None:
            raise ValueError("Latitude and longitude are required when areaId is not provided.")
        resolved_area_id, _inside = match_or_create_area(latitude, longitude)
        area = get_area_by_id(resolved_area_id)

    if area is None:
        raise ValueError("Unable to resolve a disaster area for simulation.")

    existing_session = get_active_simulation(area_id=area["id"])
    if existing_session is not None:
        stop_simulation(simulation_id=existing_session["id"], stop_reason="replaced")
        area = get_area_by_id(area["id"])
        if area is None:
            raise ValueError("Failed to restore the existing area before replacement.")

    center_lat = latitude if latitude is not None else area["centerLat"]
    center_lon = longitude if longitude is not None else area["centerLon"]
    effective_radius = float(radius_m or area.get("warningRadiusM") or DEFAULT_WARNING_RADIUS_M)
    threshold_profile = build_forced_threshold_profile(severity, custom_threshold_profile)
    original_area_profile = build_area_profile_snapshot(area)
    demo_area_profile = build_demo_area_profile(effective_radius, severity)

    area_collection.update_one({"id": area["id"]}, {"$set": demo_area_profile}, upsert=False)
    updated_area = get_area_by_id(area["id"])
    if updated_area is None:
        raise ValueError("Failed to update the disaster area for simulation.")

    now = datetime.utcnow()
    ends_at = (
        (now + timedelta(seconds=duration_seconds)).isoformat()
        if duration_seconds and duration_seconds > 0
        else None
    )
    session_doc = {
        "id": generate_simulation_id(now),
        "areaId": area["id"],
        "isActive": True,
        "disasterType": disaster_type,
        "severity": severity.lower(),
        "centerLat": center_lat,
        "centerLon": center_lon,
        "radiusM": effective_radius,
        "thresholdProfile": threshold_profile,
        "startedAt": now.isoformat(),
        "endsAt": ends_at,
        "stoppedAt": None,
        "originalAreaProfile": original_area_profile,
        "lastAssessmentSummary": None,
        "totalCitizens": max(total_citizens or 0, 0),
        "intervalSeconds": max(interval_seconds or 0, 0),
    }
    simulation_collection.insert_one(session_doc)
    logger.info("Simulation %s started for area %s.", session_doc["id"], area["id"])
    return session_doc, updated_area


def update_simulation_assessment_summary(session_id: str, assessment: dict[str, Any] | None):
    if not assessment:
        return None

    risk = assessment.get("risk") if isinstance(assessment.get("risk"), dict) else assessment
    summary = {
        "location": risk.get("location"),
        "overallRisk": risk.get("overall_risk"),
        "weatherRisk": (risk.get("weather") or {}).get("risk_level"),
        "newsRisk": (risk.get("news") or {}).get("risk_level"),
        "alertMessage": assessment.get("alert_message"),
        "updatedAt": datetime.utcnow().isoformat(),
    }
    return simulation_collection.find_one_and_update(
        {"id": session_id},
        {"$set": {"lastAssessmentSummary": summary}},
        return_document=ReturnDocument.AFTER,
    )
