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
from utils import generate_area_id, haversine_distance_m, serialize_mongo

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
weather_agent = WeatherAgent()


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


@app.post("/assess")
def assess(request: LocationRequest):
    lat, lon = None, None
    try:
        if "," in request.location:
            parts = request.location.split(",")
            lat = float(parts[0])
            lon = float(parts[1])
    except:
        pass
        
    result = coordinator.handle_request(request.location, lat=lat, lon=lon)
    return serialize_mongo(result)


@app.get("/live-weather/{area_id}")
def get_live_weather(
    area_id: str,
    lat: float = Query(None, description="Latitude coordinate"),
    lon: float = Query(None, description="Longitude coordinate"),
):
    """
    Get live weather readings for a specific area.
    Accepts coordinates or location name, fetches current weather data,
    stores it in MongoDB, and returns sensor readings.
    """
    try:
        if lat is not None and lon is not None:
            location = f"{lat},{lon}"
        else:
            location = area_id

        weather_report = weather_agent.run(location)

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
                    "coordinates": {"lat": lat, "lon": lon} if lat and lon else None,
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

