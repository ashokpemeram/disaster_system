from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from agents.coordinator import CoordinatorAgent
from agents.weather_agent import WeatherAgent
from db import weather_collection
from utils import serialize_mongo
from tools.weather_tool import fetch_weather
from datetime import datetime

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

def get_location_name_from_coordinates(lat: float, lon: float) -> str:
    """
    Convert coordinates to location name using reverse geocoding.
    Uses weatherapi.com's query parameter to get location name.
    """
    try:
        # For weatherapi.com, we can use the coordinates directly
        # Format: "lat,lon"
        return f"{lat},{lon}"
    except Exception as e:
        print(f"Error in reverse geocoding: {e}")
        return f"{lat},{lon}"

@app.post("/assess")
def assess(request: LocationRequest):
    result = coordinator.handle_request(request.location)
    return serialize_mongo(result)


@app.get("/live-weather/{area_id}")
def get_live_weather(
    area_id: str,
    lat: float = Query(None, description="Latitude coordinate"),
    lon: float = Query(None, description="Longitude coordinate"),
):
    """
    Get REAL, FRESH live weather readings for a specific area.
    
    Accepts coordinates or location name, fetches current weather data from WeatherAPI,
    stores it in MongoDB, and returns accurate sensor readings.
    """
    try:
        location = None
        
        # 1. Determine location from coordinates or parameters
        if lat is not None and lon is not None:
            # Convert coordinates to location name format
            location = f"{lat},{lon}"
        else:
            # Fallback to area_id if it looks like a location name
            location = area_id
        
        print(f"Fetching weather for area {area_id} at location: {location}")
        
        # 2. Fetch FRESH data from WeatherAPI using the weather_agent
        weather_report = weather_agent.run(location)
        
        if not weather_report or "raw_data" not in weather_report:
            return {
                "success": False,
                "message": f"Could not fetch weather data for area {area_id}",
                "readings": []
            }
        
        # 3. Store the fresh weather data in MongoDB
        # Update existing record or create new one
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
                    "updated_at": datetime.utcnow()
                }
            },
            upsert=True
        )
        
        # 4. Extract weather data and format as sensor readings
        raw_data = weather_report.get("raw_data", {}).get("current", {})
        timestamp = datetime.utcnow().isoformat()
        
        readings = [
            {
                "type": "Temperature",
                "value": raw_data.get("temp_c", 0),
                "unit": "°C",
                "trend": "stable",
                "timestamp": timestamp
            },
            {
                "type": "Wind Speed",
                "value": raw_data.get("wind_kph", 0),
                "unit": "km/h",
                "trend": "stable",
                "timestamp": timestamp
            },
            {
                "type": "Humidity",
                "value": raw_data.get("humidity", 0),
                "unit": "%",
                "trend": "stable",
                "timestamp": timestamp
            },
            {
                "type": "Rainfall",
                "value": raw_data.get("precip_mm", 0),
                "unit": "mm",
                "trend": "stable",
                "timestamp": timestamp
            }
        ]
        
        print(f"✓ Stored and returning weather data for {area_id}: {raw_data.get('condition', {}).get('text', 'Unknown')}")
        
        return {
            "success": True,
            "area_id": area_id,
            "location": location,
            "risk_level": weather_report.get("risk_level", "low"),
            "condition": raw_data.get("condition", {}).get("text", "Unknown"),
            "readings": readings,
            "timestamp": timestamp
        }
    
    except Exception as e:
        print(f"Error fetching weather: {str(e)}")
        return {
            "success": False,
            "message": f"Error retrieving weather data: {str(e)}",
            "readings": []
        }


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