import random
from datetime import datetime
from pymongo import MongoClient
import os
from dotenv import load_dotenv
import math
import sys
import argparse

load_dotenv()

# Configuration
MUMBAI_LAT = 37.421998
MUMBAI_LON = -122.084000
AREA_ID = "AREA-20260317-MUM1"

def generate_random_point(center_lat, center_lon, radius_m):
    """Generates a random lat/lon within a radius (meters) of a center point."""
    radius_deg = radius_m / 111320.0
    u = random.random()
    v = random.random()
    w = radius_deg * math.sqrt(u)
    t = 2 * math.pi * v
    lat_offset = w * math.cos(t)
    lon_offset = w * math.sin(t) / math.cos(center_lat * math.pi / 180)
    return center_lat + lat_offset, center_lon + lon_offset

def setup_scenario():
    try:
        client = MongoClient(os.getenv("MONGO_URI"))
        db = client["disaster_system"]
        
        # 1. Clear existing disaster data (DISABLED - preserving user data)
        print("ℹ️ Preserving existing disaster data...")
        # db.sos_requests.delete_many({})
        # db.aid_requests.delete_many({})
        # db.disaster_areas.delete_many({})
        db.weather_reports.delete_many({"location": "Mumbai"})

        # 2. Create Active Disaster Area
        if db.disaster_areas.find_one({"id": AREA_ID}):
            print(f"📍 Area {AREA_ID} already exists. Skipping insertion.")
        else:
            print(f"📍 Creating active area: {AREA_ID}")
            db.disaster_areas.insert_one({
                "id": AREA_ID,
                "centerLat": MUMBAI_LAT,
                "centerLon": MUMBAI_LON,
                "redRadiusM": 1500.0,
                "warningRadiusM": 3000.0,
                "greenRadiusM": 4500.0,
                "controllableRadiusM": 6000.0,
                "createdAt": datetime.utcnow().isoformat(),
                "isActive": True,
                "type": "Coastal Flood",
                "severity": "high"
            })

        # 3. Generate SOS Cluster (15 requests)
        print("🆘 Generating SOS requests...")
        for i in range(15):
            lat, lon = generate_random_point(MUMBAI_LAT, MUMBAI_LON, 1200) # Mostly in Red Zone
            db.sos_requests.insert_one({
                "id": f"SOS-MUM-{i:03d}",
                "status": "pending",
                "callerName": f"Citizen {i+1}",
                "phoneNumber": f"+91 98765 {random.randint(10000, 99999)}",
                "address": "Simulated flood zone, Mumbai coastal area",
                "latitude": lat,
                "longitude": lon,
                "timestamp": datetime.utcnow().isoformat(),
                "areaId": AREA_ID,
                "insideControllableZone": True,
                "source": "simulation"
            })

        # 4. Generate Aid Requests (10 requests)
        print("📦 Generating Aid requests...")
        resources_pool = ["Food", "Clean Water", "Medical Kit", "Blankets", "Baby Supplies"]
        for i in range(10):
            lat, lon = generate_random_point(MUMBAI_LAT, MUMBAI_LON, 2500) # Spread in Warning Zone
            db.aid_requests.insert_one({
                "id": f"AID-MUM-{i:03d}",
                "priority": random.choice(["high", "high", "medium"]),
                "status": "pending",
                "requesterName": f"Resident {i+1}",
                "resources": random.sample(resources_pool, k=random.randint(1, 3)),
                "peopleCount": random.randint(1, 10),
                "location": "Coastal Housing Community",
                "latitude": lat,
                "longitude": lon,
                "timestamp": datetime.utcnow().isoformat(),
                "areaId": AREA_ID,
                "insideControllableZone": True,
                "details": "Trapped on upper floors due to rising water levels."
            })

        # 5. Mock High Risk Weather
        print("⛈️  Mocking extreme weather report...")
        db.weather_reports.insert_one({
            "location": "Mumbai",
            "risk_level": "high",
            "indicators": ["heavy_rain", "heavy_precipitation", "heavy_wind", "storm_level_wind"],
            "raw_data": {
                "current": {
                    "temp_c": 28.5,
                    "wind_kph": 92.0,
                    "condition": {"text": "Extremely Heavy Rain and Cyclone Warning"},
                    "precip_mm": 18.5,
                    "vis_km": 0.8,
                    "uv": 2.0
                }
            },
            "timestamp": datetime.utcnow().isoformat()
        })

        print("\n✅ Scenario 'COASTAL FLOOD MUMBAI' generated successfully!")
        print("👉 You can now open your Citizen app and Admin dashboard to see the live disaster mode.")

    except Exception as e:
        print(f"❌ Error setting up scenario: {e}")

def main():
    parser = argparse.ArgumentParser(description="CERCA Disaster Simulation Facility")
    parser.add_argument("--setup", action="store_true", help="Clear and setup a fresh disaster scenario")
    parser.add_argument("--clear", action="store_true", help="Clear all simulated disaster data")
    
    args = parser.parse_args()
    
    if args.clear:
        try:
            client = MongoClient(os.getenv("MONGO_URI"))
            db = client["disaster_system"]
            print("🧹 Clearing all simulated disaster data...")
            db.sos_requests.delete_many({})
            db.aid_requests.delete_many({})
            db.disaster_areas.delete_many({})
            db.weather_reports.delete_many({"location": "Mumbai"})
            print("✅ All clear!")
        except Exception as e:
            print(f"❌ Error clearing scenario: {e}")
    else:
        # Default behavior is to setup
        setup_scenario()

if __name__ == "__main__":
    main()
