from datetime import datetime
from typing import List, Optional
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from agents.coordinator import CoordinatorAgent
from utils import serialize_mongo, generate_area_id, haversine_distance_m
from db import aid_request_collection, area_collection, sos_request_collection

_AREA_MATCH_DISTANCE_M = 2500.0

app = FastAPI()

# Allow Flutter app (emulator/device/desktop) to reach this API
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

coordinator = CoordinatorAgent()

class LocationRequest(BaseModel):
    location: str


class AidRequestPayload(BaseModel):
    id: Optional[str] = None
    priority: str = "medium"
    status: str = "pending"
    requesterName: str = "Citizen"
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


def _get_active_areas():
    return list(area_collection.find({"isActive": True}))


def _create_area_for_point(lat: float, lon: float):
    existing_ids = set(
        a.get("id") for a in area_collection.find({}, {"id": 1}) if a.get("id")
    )
    area_id = generate_area_id(existing_ids)
    now = datetime.utcnow().isoformat()
    area = {
        "id": area_id,
        "centerLat": lat,
        "centerLon": lon,
        "redRadiusM": 300.0,
        "warningRadiusM": 600.0,
        "greenRadiusM": 900.0,
        "controllableRadiusM": 1200.0,
        "createdAt": now,
        "isActive": True,
    }
    area_collection.insert_one(area)
    return area


def _match_or_create_area(lat: float, lon: float):
    areas = _get_active_areas()
    if not areas:
        created = _create_area_for_point(lat, lon)
        return created["id"], True

    nearest = None
    nearest_distance = float("inf")
    for area in areas:
        dist = haversine_distance_m(lat, lon, area["centerLat"], area["centerLon"])
        if dist < nearest_distance:
            nearest_distance = dist
            nearest = area

    resolved = nearest or areas[0]
    inside = nearest_distance <= resolved.get("controllableRadiusM", 0.0)

    match_distance = resolved.get("controllableRadiusM", 0.0) or _AREA_MATCH_DISTANCE_M
    if nearest_distance <= match_distance:
        return resolved["id"], inside

    created = _create_area_for_point(lat, lon)
    return created["id"], True

    nearest = None
    nearest_distance = float("inf")
    for area in areas:
        dist = haversine_distance_m(lat, lon, area["centerLat"], area["centerLon"])
        if dist < nearest_distance:
            nearest_distance = dist
            nearest = area

    resolved = nearest or areas[0]
    inside = nearest_distance <= resolved.get("controllableRadiusM", 0.0)
    return resolved["id"], inside

@app.post("/assess")
def assess(request: LocationRequest):
    result = coordinator.handle_request(request.location)
    return serialize_mongo(result)


@app.post("/aid-requests")
def create_aid_request(payload: AidRequestPayload):
    data = payload.dict()
    if not data.get("id"):
        data["id"] = f"AID-{int(datetime.utcnow().timestamp() * 1000)}"
    if not data.get("timestamp"):
        data["timestamp"] = datetime.utcnow().isoformat()

    area_id, inside = _match_or_create_area(data["latitude"], data["longitude"])
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

    area_id, inside = _match_or_create_area(data["latitude"], data["longitude"])
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
    query = {"isActive": True} if active else {}
    records = list(area_collection.find(query).sort("createdAt", -1))
    return serialize_mongo(records)


# @app.post("/assess")
# def assess(request: LocationRequest):
#     result = coordinator.handle_request(request.location)

#     clean_response = {
#         "location": result["risk"]["location"],
#         "overall_risk": result["risk"]["overall_risk"],
#         "temperature_c": result["risk"]["weather"]["raw_data"]["current"]["temp_c"],
#         "condition": result["risk"]["weather"]["raw_data"]["current"]["condition"]["text"],
#         "alert": result.get("alert_message", None)
#     }

#     return clean_response
