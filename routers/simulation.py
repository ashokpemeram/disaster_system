from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, HTTPException, status
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel, Field

from agents.coordinator import CoordinatorAgent
from services.area_service import get_area_by_id
from services.simulation_service import (
    get_active_simulation,
    start_simulation,
    stop_simulation,
    update_simulation_assessment_summary,
)
from utils import serialize_mongo

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/simulation", tags=["simulation"])
coordinator = CoordinatorAgent()


class SimulationStartPayload(BaseModel):
    areaId: str | None = None
    latitude: float | None = None
    longitude: float | None = None
    radiusM: float | None = Field(default=None, gt=0)
    disasterType: str
    severity: str
    durationSeconds: int | None = Field(default=None, gt=0)
    thresholdProfile: dict[str, Any] | None = None
    triggerAssessment: bool = True
    totalCitizens: int | None = Field(default=None, ge=0)
    intervalSeconds: int | None = Field(default=None, ge=0)


class SimulationStopPayload(BaseModel):
    areaId: str | None = None
    simulationId: str | None = None


@router.post("/start", status_code=status.HTTP_200_OK)
async def start_simulation_route(payload: SimulationStartPayload):
    if payload.areaId is None and (payload.latitude is None or payload.longitude is None):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="areaId or both latitude/longitude are required.",
        )
    try:
        session, area = await run_in_threadpool(
            start_simulation,
            area_id=payload.areaId,
            latitude=payload.latitude,
            longitude=payload.longitude,
            radius_m=payload.radiusM,
            disaster_type=payload.disasterType,
            severity=payload.severity,
            duration_seconds=payload.durationSeconds,
            custom_threshold_profile=payload.thresholdProfile,
            total_citizens=payload.totalCitizens,
            interval_seconds=payload.intervalSeconds,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("Failed to start simulation.")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to start simulation.",
        ) from exc

    assessment = None
    if payload.triggerAssessment:
        location = f"{area['centerLat']},{area['centerLon']}"
        assessment = await run_in_threadpool(
            coordinator.handle_request,
            location,
            False,
            None,
            area["id"],
        )
        updated_session = await run_in_threadpool(
            update_simulation_assessment_summary,
            session["id"],
            assessment,
        )
        if updated_session is not None:
            session = updated_session

    return serialize_mongo(
        {
            "message": "Simulation started successfully.",
            "session": session,
            "area": area,
            "assessment": assessment,
        }
    )


@router.post("/stop", status_code=status.HTTP_200_OK)
async def stop_simulation_route(payload: SimulationStopPayload):
    if payload.areaId is None and payload.simulationId is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="areaId or simulationId is required.",
        )
    session, area = await run_in_threadpool(
        stop_simulation,
        simulation_id=payload.simulationId,
        area_id=payload.areaId,
    )
    if session is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Active simulation not found.",
        )

    return serialize_mongo(
        {
            "message": "Simulation stopped successfully.",
            "session": session,
            "area": area,
        }
    )


@router.get("/active", status_code=status.HTTP_200_OK)
async def get_active_simulation_route(area_id: str | None = None):
    if not area_id:
        return {"message": "No area specified.", "session": None, "area": None}

    session = await run_in_threadpool(get_active_simulation, area_id=area_id)
    area = await run_in_threadpool(get_area_by_id, area_id)
    return serialize_mongo(
        {
            "message": "Active simulation fetched successfully."
            if session
            else "No active simulation for this area.",
            "session": session,
            "area": area,
        }
    )
