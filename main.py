from datetime import datetime
from typing import List, Optional

from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from agents.coordinator import CoordinatorAgent
from agents.weather_agent import WeatherAgent
from db import (
    aid_request_collection,
    area_collection,
    sos_request_collection,
    weather_collection,
)
from routers.admin import router as admin_router
from routers.simulation import router as simulation_router
from services.area_service import (
    find_matching_area,
    match_or_create_area,
    normalize_area,
    parse_location_coordinates,
)
from utils import serialize_mongo

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(admin_router)
app.include_router(simulation_router)

coordinator = CoordinatorAgent()
weather_agent = WeatherAgent()


class LocationRequest(BaseModel):
    location: str
    simulate: bool = False
    scenario: Optional[str] = None
    areaId: Optional[str] = None


class AidRequestPayload(BaseModel):
    id: Optional[str] = None
    priority: str = "medium"
    status: str = "pending"
    requesterName: Optional[str] = None
    phoneNumber: Optional[str] = None
    resources: List[str]
    peopleCount: int
    location: str
    latitude: float
    longitude: float
    timestamp: Optional[str] = None
    areaId: str = "UNASSIGNED"
    insideControllableZone: bool = False
    details: Optional[str] = None


class SosRequestPayload(BaseModel):
    id: Optional[str] = None
    status: str = "pending"
    callerName: str
    phoneNumber: str
    address: str
    latitude: float
    longitude: float
    timestamp: Optional[str] = None
    eta: Optional[str] = None
    areaId: str = "UNASSIGNED"
    insideControllableZone: bool = False
    source: str = "citizen"
    disasterId: Optional[str] = None


def _resolve_assessment_area_id(location: str, area_id: Optional[str]) -> Optional[str]:
    if area_id:
        return area_id

    lat, lon = parse_location_coordinates(location)
    if lat is None or lon is None:
        return None

    matched_area, _inside, _distance = find_matching_area(lat, lon)
    return matched_area["id"] if matched_area is not None else None


@app.post("/assess")
def assess(request: LocationRequest):
    resolved_area_id = _resolve_assessment_area_id(request.location, request.areaId)
    result = coordinator.handle_request(
        request.location,
        simulate=request.simulate,
        scenario=request.scenario,
        area_id=resolved_area_id,
    )
    return serialize_mongo(result)


@app.get("/live-weather/{area_id}")
def get_live_weather(
    area_id: str,
    lat: float = Query(None, description="Latitude coordinate"),
    lon: float = Query(None, description="Longitude coordinate"),
):
    try:
        location = f"{lat},{lon}" if lat is not None and lon is not None else area_id
        weather_report = weather_agent.run(location, area_id=area_id)

        if not weather_report or "raw_data" not in weather_report:
            return {
                "success": False,
                "message": f"Could not fetch weather data for area {area_id}",
                "readings": [],
            }

        weather_collection.update_one(
            {"location": area_id},
            {
                "$set": {
                    "location": area_id,
                    "coordinates": {"lat": lat, "lon": lon}
                    if lat is not None and lon is not None
                    else None,
                    "raw_data": weather_report.get("raw_data"),
                    "risk_level": weather_report.get("risk_level", "low"),
                    "indicators": weather_report.get("indicators", []),
                    "timestamp": datetime.utcnow().isoformat(),
                    "updated_at": datetime.utcnow(),
                }
            },
            upsert=True,
        )

        raw_data = weather_report.get("raw_data", {}).get("current", {})
        timestamp = datetime.utcnow().isoformat()

        readings = [
            {
                "type": "Temperature",
                "value": raw_data.get("temp_c", 0),
                "unit": "C",
                "trend": "stable",
                "timestamp": timestamp,
            },
            {
                "type": "Wind Speed",
                "value": raw_data.get("wind_kph", 0),
                "unit": "km/h",
                "trend": "stable",
                "timestamp": timestamp,
            },
            {
                "type": "Humidity",
                "value": raw_data.get("humidity", 0),
                "unit": "%",
                "trend": "stable",
                "timestamp": timestamp,
            },
            {
                "type": "Rainfall",
                "value": raw_data.get("precip_mm", 0),
                "unit": "mm",
                "trend": "stable",
                "timestamp": timestamp,
            },
        ]

        return {
            "success": True,
            "area_id": area_id,
            "location": location,
            "risk_level": weather_report.get("risk_level", "low"),
            "condition": raw_data.get("condition", {}).get("text", "Unknown"),
            "readings": readings,
            "timestamp": timestamp,
        }
    except Exception as e:
        return {
            "success": False,
            "message": f"Error retrieving weather data: {str(e)}",
            "readings": [],
        }


@app.post("/aid-requests")
def create_aid_request(payload: AidRequestPayload):
    data = payload.dict()
    if not data.get("id"):
        data["id"] = f"AID-{int(datetime.utcnow().timestamp() * 1000)}"
    if not data.get("timestamp"):
        data["timestamp"] = datetime.utcnow().isoformat()
    requester_name = (data.get("requesterName") or "").strip()
    phone_number = (data.get("phoneNumber") or "").strip()
    data["requesterName"] = requester_name or "Citizen"
    data["phoneNumber"] = phone_number or None

    area_id, inside = match_or_create_area(data["latitude"], data["longitude"])
    data["areaId"] = area_id
    data["insideControllableZone"] = inside

    aid_request_collection.insert_one(data)
    updated = aid_request_collection.find_one({"id": data["id"]})
    return serialize_mongo(updated or data)


@app.post("/sos-requests")
def create_sos_request(payload: SosRequestPayload):
    data = payload.dict()
    if not data.get("id"):
        data["id"] = f"SOS-{int(datetime.utcnow().timestamp() * 1000)}"
    if not data.get("timestamp"):
        data["timestamp"] = datetime.utcnow().isoformat()

    area_id, inside = match_or_create_area(data["latitude"], data["longitude"])
    data["areaId"] = area_id
    data["insideControllableZone"] = inside

    sos_request_collection.insert_one(data)
    updated = sos_request_collection.find_one({"id": data["id"]})
    return serialize_mongo(updated or data)


@app.get("/aid-requests")
def list_aid_requests(area_id: Optional[str] = None):
    query = {}
    if area_id:
        query["areaId"] = area_id

    records = list(aid_request_collection.find(query).sort("timestamp", -1))
    return serialize_mongo(records)


@app.get("/sos-requests")
def list_sos_requests(area_id: Optional[str] = None):
    query = {}
    if area_id:
        query["areaId"] = area_id

    records = list(sos_request_collection.find(query).sort("timestamp", -1))
    return serialize_mongo(records)


@app.get("/areas")
def list_active_areas(active: bool = True):
    query = (
        {
            "$or": [
                {"isActive": True},
                {"isActive": {"$exists": False}, "closedAt": None},
            ]
        }
        if active
        else {}
    )
    records = list(area_collection.find(query).sort("createdAt", -1))
    normalized_records = [
        normalized
        for normalized in (normalize_area(area) for area in records)
        if normalized is not None
    ]
    return serialize_mongo(normalized_records)
