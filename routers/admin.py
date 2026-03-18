import logging
from datetime import datetime
from typing import Any

from fastapi.concurrency import run_in_threadpool
from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field
from pymongo import ReturnDocument
from pymongo.errors import PyMongoError

from db import (
    aid_request_collection,
    area_collection,
    incident_history_collection,
    mongo_available,
    sos_request_collection,
)
from services.history_service import normalize_archived_incident
from services.simulation_service import stop_simulation
from utils import serialize_mongo

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin", tags=["admin"])


class ArchiveIncidentPayload(BaseModel):
    id: str | None = None
    disasterType: str
    severity: str
    startedAt: str | None = None
    closedAt: str | None = None
    affectedCount: int = 0
    evacuatedCount: int = 0
    totalSosLogs: int = 0
    pendingSosCount: int = 0
    dispatchedSosCount: int = 0
    totalAidRequests: int = 0
    pendingAidCount: int = 0
    dispatchedAidCount: int = 0
    totalDispatched: int = 0
    safeCampCount: int = 0
    wasSimulation: bool = False
    simulationId: str | None = None
    simulatedCitizens: int = 0
    currentRisk: str | None = None
    alertMessage: str | None = None
    finalOutcomeSummary: str | None = None
    areaSummary: str | None = None
    requestedResources: dict[str, int] = Field(default_factory=dict)
    aiResourceSnapshot: dict[str, int] = Field(default_factory=dict)
    keyActions: list[str] = Field(default_factory=list)
    area: dict[str, Any] = Field(default_factory=dict)
    sosLogs: list[dict[str, Any]] = Field(default_factory=list)
    aidLogs: list[dict[str, Any]] = Field(default_factory=list)
    safeCamps: list[dict[str, Any]] = Field(default_factory=list)
    communicationLogs: list[dict[str, Any]] = Field(default_factory=list)
    weatherHistory: list[dict[str, Any]] = Field(default_factory=list)
    decisionHistory: list[dict[str, Any]] = Field(default_factory=list)


async def _persisted_find_one_and_update(
    *,
    collection,
    record_id: str,
    update_fields: dict[str, Any],
    entity_label: str,
    current_field: str,
    already_updated_value: Any,
    already_updated_message: str,
):
    """
    Persist a MongoDB update and return the updated document.

    Example DB interaction code:
    updated_record = await run_in_threadpool(
        collection.find_one_and_update,
        {"id": record_id, current_field: {"$ne": already_updated_value}},
        {"$set": update_fields},
        return_document=ReturnDocument.AFTER,
    )
    """

    if not mongo_available:
        logger.error("Database unavailable while updating %s %s", entity_label, record_id)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database is unavailable.",
        )

    try:
        updated_record = await run_in_threadpool(
            collection.find_one_and_update,
            {"id": record_id, current_field: {"$ne": already_updated_value}},
            {"$set": update_fields},
            return_document=ReturnDocument.AFTER,
        )
    except PyMongoError as exc:
        logger.exception("MongoDB update error for %s %s", entity_label, record_id)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database is unavailable.",
        ) from exc
    except Exception as exc:
        logger.exception("Unexpected database update error for %s %s", entity_label, record_id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to update {entity_label}.",
        ) from exc

    if updated_record is not None:
        logger.info(
            "Persisted %s update for id=%s with fields=%s",
            entity_label,
            record_id,
            update_fields,
        )
        return serialize_mongo(updated_record)

    try:
        existing_record = await run_in_threadpool(collection.find_one, {"id": record_id})
    except PyMongoError as exc:
        logger.exception("MongoDB verification error for %s %s", entity_label, record_id)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database is unavailable.",
        ) from exc
    except Exception as exc:
        logger.exception("Unexpected database verification error for %s %s", entity_label, record_id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to verify {entity_label}.",
        ) from exc

    if existing_record is None:
        logger.warning("%s %s not found.", entity_label, record_id)
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"{entity_label} not found.",
        )

    if existing_record.get(current_field) == already_updated_value:
        logger.info("%s %s already updated. Skipping write.", entity_label, record_id)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=already_updated_message,
        )

    logger.error("%s %s could not be updated for an unknown reason.", entity_label, record_id)
    raise HTTPException(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        detail=f"Failed to update {entity_label}.",
    )


@router.put("/sos/{id}/dispatch", status_code=status.HTTP_200_OK)
async def dispatch_sos(id: str):
    return await _persisted_find_one_and_update(
        collection=sos_request_collection,
        record_id=id,
        update_fields={"status": "successful"},
        entity_label="SOSLog",
        current_field="status",
        already_updated_value="successful",
        already_updated_message="SOSLog is already marked as successful.",
    )


@router.put("/aid/{id}/dispatch", status_code=status.HTTP_200_OK)
async def dispatch_aid(id: str):
    return await _persisted_find_one_and_update(
        collection=aid_request_collection,
        record_id=id,
        update_fields={"status": "successful"},
        entity_label="AidRequest",
        current_field="status",
        already_updated_value="successful",
        already_updated_message="AidRequest is already marked as successful.",
    )


@router.put("/disaster/{id}/close", status_code=status.HTTP_200_OK)
async def close_disaster_area(id: str):
    return await _persisted_find_one_and_update(
        collection=area_collection,
        record_id=id,
        update_fields={
            "isActive": False,
            "closedAt": datetime.utcnow().isoformat(),
        },
        entity_label="DisasterArea",
        current_field="isActive",
        already_updated_value=False,
        already_updated_message="DisasterArea is already closed.",
    )


@router.get("/history", status_code=status.HTTP_200_OK)
async def list_archived_history():
    if not mongo_available:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database is unavailable.",
        )

    try:
        records = await run_in_threadpool(
            lambda: list(
                incident_history_collection.find({}).sort("closedAt", -1)
            )
        )
    except PyMongoError as exc:
        logger.exception("MongoDB error while fetching archived history")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database is unavailable.",
        ) from exc
    except Exception as exc:
        logger.exception("Unexpected error while fetching archived history")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to fetch archived history.",
        ) from exc

    return serialize_mongo(records)


@router.get("/history/{id}", status_code=status.HTTP_200_OK)
async def get_archived_history(id: str):
    if not mongo_available:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database is unavailable.",
        )

    try:
        record = await run_in_threadpool(incident_history_collection.find_one, {"id": id})
    except PyMongoError as exc:
        logger.exception("MongoDB error while fetching archived history %s", id)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database is unavailable.",
        ) from exc
    except Exception as exc:
        logger.exception("Unexpected error while fetching archived history %s", id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to fetch archived history.",
        ) from exc

    if record is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Archived incident not found.",
        )

    return serialize_mongo(record)


@router.post("/disaster/{id}/archive-close", status_code=status.HTTP_200_OK)
async def archive_and_close_disaster_area(id: str, payload: ArchiveIncidentPayload):
    if not mongo_available:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database is unavailable.",
        )

    try:
        area = await run_in_threadpool(area_collection.find_one, {"id": id})
    except PyMongoError as exc:
        logger.exception("MongoDB error while loading area %s for archive-close", id)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database is unavailable.",
        ) from exc

    if area is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="DisasterArea not found.",
        )

    if area.get("isActive") is False:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="DisasterArea is already closed.",
        )

    closed_at = datetime.utcnow().isoformat()

    try:
        await run_in_threadpool(
            stop_simulation,
            area_id=id,
            stop_reason="area_closed",
        )
        closed_area = await run_in_threadpool(
            area_collection.find_one_and_update,
            {"id": id, "isActive": {"$ne": False}},
            {"$set": {"isActive": False, "closedAt": closed_at}},
            return_document=ReturnDocument.AFTER,
        )
    except PyMongoError as exc:
        logger.exception("MongoDB error while closing area %s for archive-close", id)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database is unavailable.",
        ) from exc
    except Exception as exc:
        logger.exception("Unexpected error while closing area %s for archive-close", id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to close disaster area.",
        ) from exc

    if closed_area is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="DisasterArea is already closed.",
        )

    incident_doc = normalize_archived_incident(
        payload.dict(),
        area_id=id,
        closed_area=closed_area,
        closed_at_iso=closed_at,
    )

    try:
        await run_in_threadpool(incident_history_collection.insert_one, incident_doc)
        stored_incident = await run_in_threadpool(
            incident_history_collection.find_one,
            {"id": incident_doc["id"]},
        )
    except PyMongoError as exc:
        logger.exception("MongoDB error while archiving history for area %s", id)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database is unavailable.",
        ) from exc
    except Exception as exc:
        logger.exception("Unexpected error while archiving history for area %s", id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to archive disaster history.",
        ) from exc

    logger.info(
        "Archived incident %s while closing area %s.",
        incident_doc["id"],
        id,
    )
    return {
        "message": "Area closed and archived successfully.",
        "area": serialize_mongo(closed_area),
        "incident": serialize_mongo(stored_incident or incident_doc),
    }
