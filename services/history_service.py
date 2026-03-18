from __future__ import annotations

from copy import deepcopy
from datetime import datetime
import random
from typing import Any


_INCIDENT_ID_CHARS = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"


def generate_incident_id(now: datetime | None = None) -> str:
    stamp = (now or datetime.utcnow()).strftime("%Y%m%d%H%M%S")
    suffix = "".join(random.choice(_INCIDENT_ID_CHARS) for _ in range(4))
    return f"INC-{stamp}-{suffix}"


def _coerce_int(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _coerce_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "y"}
    return bool(value)


def _clone_list_of_dicts(values: Any) -> list[dict[str, Any]]:
    if not isinstance(values, list):
        return []
    return [deepcopy(item) for item in values if isinstance(item, dict)]


def _clone_string_list(values: Any) -> list[str]:
    if not isinstance(values, list):
        return []
    return [str(item) for item in values if str(item).strip()]


def _clone_int_map(value: Any) -> dict[str, int]:
    if not isinstance(value, dict):
        return {}
    return {
        str(key): _coerce_int(raw_value)
        for key, raw_value in value.items()
        if str(key).strip()
    }


def build_area_summary(area_snapshot: dict[str, Any]) -> str:
    radius = area_snapshot.get("warningRadiusM") or area_snapshot.get("redRadiusM")
    label = area_snapshot.get("label") or area_snapshot.get("summaryLabel")
    if label:
        return str(label)
    if radius:
        try:
            return f"{float(radius):.0f} m impact radius"
        except (TypeError, ValueError):
            return "Archived impact area"
    return "Archived impact area"


def normalize_archived_incident(
    payload: dict[str, Any],
    *,
    area_id: str,
    closed_area: dict[str, Any],
    closed_at_iso: str,
) -> dict[str, Any]:
    now = datetime.utcnow()
    area_payload = deepcopy(payload.get("area") or {})
    area_payload.update(
        {
            "id": area_id,
            "areaId": area_id,
            "isActive": False,
            "closedAt": closed_at_iso,
            "centerLat": area_payload.get("centerLat", closed_area.get("centerLat")),
            "centerLon": area_payload.get("centerLon", closed_area.get("centerLon")),
            "redRadiusM": area_payload.get("redRadiusM", closed_area.get("redRadiusM")),
            "warningRadiusM": area_payload.get(
                "warningRadiusM",
                closed_area.get("warningRadiusM"),
            ),
            "greenRadiusM": area_payload.get("greenRadiusM", closed_area.get("greenRadiusM")),
            "controllableRadiusM": area_payload.get(
                "controllableRadiusM",
                closed_area.get("controllableRadiusM"),
            ),
            "createdAt": area_payload.get("createdAt", closed_area.get("createdAt")),
        }
    )

    started_at = (
        payload.get("startedAt")
        or area_payload.get("createdAt")
        or closed_area.get("createdAt")
        or closed_at_iso
    )
    incident_doc = {
        "id": payload.get("id") or generate_incident_id(now),
        "areaId": area_id,
        "status": "resolved",
        "severity": str(payload.get("severity") or "medium").lower(),
        "disasterType": str(payload.get("disasterType") or "Disaster"),
        "startedAt": started_at,
        "closedAt": closed_at_iso,
        "archivedAt": now.isoformat(),
        "affectedCount": _coerce_int(payload.get("affectedCount")),
        "evacuatedCount": _coerce_int(payload.get("evacuatedCount")),
        "totalSosLogs": _coerce_int(payload.get("totalSosLogs")),
        "pendingSosCount": _coerce_int(payload.get("pendingSosCount")),
        "dispatchedSosCount": _coerce_int(payload.get("dispatchedSosCount")),
        "totalAidRequests": _coerce_int(payload.get("totalAidRequests")),
        "pendingAidCount": _coerce_int(payload.get("pendingAidCount")),
        "dispatchedAidCount": _coerce_int(payload.get("dispatchedAidCount")),
        "totalDispatched": _coerce_int(payload.get("totalDispatched")),
        "safeCampCount": _coerce_int(payload.get("safeCampCount")),
        "wasSimulation": _coerce_bool(payload.get("wasSimulation")),
        "simulationId": payload.get("simulationId"),
        "simulatedCitizens": _coerce_int(payload.get("simulatedCitizens")),
        "currentRisk": payload.get("currentRisk"),
        "alertMessage": payload.get("alertMessage"),
        "finalOutcomeSummary": payload.get("finalOutcomeSummary"),
        "areaSummary": payload.get("areaSummary") or build_area_summary(area_payload),
        "area": area_payload,
        "requestedResources": _clone_int_map(payload.get("requestedResources")),
        "aiResourceSnapshot": _clone_int_map(payload.get("aiResourceSnapshot")),
        "keyActions": _clone_string_list(payload.get("keyActions")),
        "sosLogs": _clone_list_of_dicts(payload.get("sosLogs")),
        "aidLogs": _clone_list_of_dicts(payload.get("aidLogs")),
        "safeCamps": _clone_list_of_dicts(payload.get("safeCamps")),
        "communicationLogs": _clone_list_of_dicts(payload.get("communicationLogs")),
        "weatherHistory": _clone_list_of_dicts(payload.get("weatherHistory")),
        "decisionHistory": _clone_list_of_dicts(payload.get("decisionHistory")),
        "backendAreaState": deepcopy(closed_area),
    }
    return incident_doc
