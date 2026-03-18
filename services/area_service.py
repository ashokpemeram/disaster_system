from __future__ import annotations

from datetime import datetime
from math import inf
from typing import Any

from db import area_collection
from utils import generate_area_id, haversine_distance_m

AREA_MATCH_DISTANCE_M = 2500.0
DEFAULT_RED_RADIUS_M = 300.0
DEFAULT_WARNING_RADIUS_M = 600.0
DEFAULT_GREEN_RADIUS_M = 900.0
DEFAULT_CONTROLLABLE_RADIUS_M = 1200.0


def coerce_float(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def extract_point_fields(container: Any) -> tuple[float | None, float | None]:
    if not isinstance(container, dict):
        return None, None

    for lat_key, lon_key in (
        ("centerLat", "centerLon"),
        ("latitude", "longitude"),
        ("lat", "lon"),
        ("lat", "lng"),
    ):
        lat = coerce_float(container.get(lat_key))
        lon = coerce_float(container.get(lon_key))
        if lat is not None and lon is not None:
            return lat, lon

    return None, None


def parse_location_coordinates(location: str | None) -> tuple[float | None, float | None]:
    if not isinstance(location, str):
        return None, None

    parts = [part.strip() for part in location.split(",")]
    if len(parts) != 2:
        return None, None

    lat = coerce_float(parts[0])
    lon = coerce_float(parts[1])
    if lat is None or lon is None:
        return None, None
    return lat, lon


def resolve_area_center(area: dict[str, Any]) -> tuple[float | None, float | None]:
    lat, lon = extract_point_fields(area)
    if lat is not None and lon is not None:
        return lat, lon

    for nested_key in ("center", "coordinates", "location"):
        nested = area.get(nested_key)
        lat, lon = extract_point_fields(nested)
        if lat is not None and lon is not None:
            return lat, lon

        if nested_key == "coordinates" and isinstance(nested, (list, tuple)) and len(nested) >= 2:
            lon = coerce_float(nested[0])
            lat = coerce_float(nested[1])
            if lat is not None and lon is not None:
                return lat, lon

    geometry = area.get("geometry")
    if isinstance(geometry, dict):
        coordinates = geometry.get("coordinates")
        if isinstance(coordinates, (list, tuple)) and len(coordinates) >= 2:
            lon = coerce_float(coordinates[0])
            lat = coerce_float(coordinates[1])
            if lat is not None and lon is not None:
                return lat, lon

    return None, None


def resolve_controllable_radius(area: dict[str, Any]) -> float | None:
    controllable = coerce_float(area.get("controllableRadiusM"))
    if controllable is not None and controllable > 0:
        return controllable

    warning = coerce_float(area.get("warningRadiusM"))
    if warning is not None and warning > 0:
        return warning * 2.0

    green = coerce_float(area.get("greenRadiusM"))
    if green is not None and green > 0:
        return max(green + 300.0, DEFAULT_CONTROLLABLE_RADIUS_M)

    red = coerce_float(area.get("redRadiusM"))
    if red is not None and red > 0:
        return max(red * 4.0, DEFAULT_CONTROLLABLE_RADIUS_M)

    radius = coerce_float(area.get("radiusM"))
    if radius is None:
        radius = coerce_float(area.get("radiusMeters"))
    if radius is not None and radius > 0:
        return radius

    return None


def normalize_area(area: dict[str, Any] | None) -> dict[str, Any] | None:
    if area is None:
        return None

    normalized = dict(area)

    lat, lon = resolve_area_center(normalized)
    if lat is None or lon is None:
        return None

    normalized["centerLat"] = lat
    normalized["centerLon"] = lon

    if not normalized.get("id") and normalized.get("_id") is not None:
        normalized["id"] = str(normalized["_id"])
    if not normalized.get("id"):
        return None

    warning_radius = coerce_float(normalized.get("warningRadiusM"))
    red_radius = coerce_float(normalized.get("redRadiusM"))
    green_radius = coerce_float(normalized.get("greenRadiusM"))
    controllable_radius = resolve_controllable_radius(normalized)

    if red_radius is None or red_radius <= 0:
        red_radius = DEFAULT_RED_RADIUS_M
    if warning_radius is None or warning_radius <= 0:
        warning_radius = max(red_radius + 300.0, DEFAULT_WARNING_RADIUS_M)
    if controllable_radius is None or controllable_radius <= 0:
        controllable_radius = max(
            warning_radius * 2.0,
            DEFAULT_CONTROLLABLE_RADIUS_M,
        )
    if green_radius is None or green_radius <= 0:
        green_radius = max(
            min(controllable_radius - 300.0, DEFAULT_GREEN_RADIUS_M),
            warning_radius + 100.0,
        )

    normalized["redRadiusM"] = red_radius
    normalized["warningRadiusM"] = warning_radius
    normalized["greenRadiusM"] = green_radius
    normalized["controllableRadiusM"] = controllable_radius
    normalized["isActive"] = bool(
        normalized.get("isActive", normalized.get("closedAt") is None)
    )

    if not normalized.get("createdAt"):
        normalized["createdAt"] = datetime.utcnow().isoformat()

    return normalized


def get_active_areas() -> list[dict[str, Any]]:
    raw_areas = list(
        area_collection.find(
            {
                "$or": [
                    {"isActive": True},
                    {"isActive": {"$exists": False}, "closedAt": None},
                ]
            }
        )
    )
    return [
        normalized
        for normalized in (normalize_area(area) for area in raw_areas)
        if normalized is not None
    ]


def get_area_by_id(area_id: str) -> dict[str, Any] | None:
    return normalize_area(area_collection.find_one({"id": area_id}))


def create_area_for_point(lat: float, lon: float) -> dict[str, Any]:
    existing_ids = set(
        area.get("id") for area in area_collection.find({}, {"id": 1}) if area.get("id")
    )
    area_id = generate_area_id(existing_ids)
    now = datetime.utcnow().isoformat()
    area = {
        "id": area_id,
        "centerLat": lat,
        "centerLon": lon,
        "redRadiusM": DEFAULT_RED_RADIUS_M,
        "warningRadiusM": DEFAULT_WARNING_RADIUS_M,
        "greenRadiusM": DEFAULT_GREEN_RADIUS_M,
        "controllableRadiusM": DEFAULT_CONTROLLABLE_RADIUS_M,
        "createdAt": now,
        "isActive": True,
    }
    area_collection.insert_one(area)
    return normalize_area(area) or area


def find_matching_area(
    lat: float,
    lon: float,
) -> tuple[dict[str, Any] | None, bool, float]:
    areas = get_active_areas()
    if not areas:
        return None, False, inf

    nearest = None
    nearest_distance = inf
    for area in areas:
        dist = haversine_distance_m(lat, lon, area["centerLat"], area["centerLon"])
        if dist < nearest_distance:
            nearest_distance = dist
            nearest = area

    if nearest is None:
        return None, False, inf

    controllable_radius = resolve_controllable_radius(nearest)
    inside = controllable_radius is not None and nearest_distance <= controllable_radius
    match_distance = controllable_radius or AREA_MATCH_DISTANCE_M
    if nearest_distance <= match_distance:
        return nearest, inside, nearest_distance

    return None, False, nearest_distance


def match_or_create_area(lat: float, lon: float) -> tuple[str, bool]:
    area, inside, _distance = find_matching_area(lat, lon)
    if area is not None:
        return area["id"], inside

    created = create_area_for_point(lat, lon)
    return created["id"], True
