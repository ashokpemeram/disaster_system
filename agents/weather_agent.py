from tools.weather_tool import fetch_weather
from db import weather_collection

class WeatherAgent:

    def run(self, location: str):
        data = fetch_weather(location)
        print("Weather API Response:", data)

        indicators = []
        risk_level = "low"

        temp = data["current"]["temp_c"]
        wind = data["current"]["wind_kph"]
        condition = data["current"]["condition"]["text"].lower()
        precip = data["current"].get("precip_mm", 0)
        vis = data["current"].get("vis_km", 0)
        uv = data["current"].get("uv", 0)

        # Wind Risk (Existing)
        if wind > 50:
            risk_level = "medium"
            indicators.append("heavy_wind")
        if wind > 80:
            risk_level = "high"
            indicators.append("storm_level_wind")

        # Rain/Precipitation Risk
        if "rain" in condition or precip > 5:
            risk_level = "medium" if risk_level != "high" else "high"
            indicators.append("heavy_rain")
        if precip > 10:
            risk_level = "high"
            indicators.append("heavy_precipitation")

        # Temperature Risk
        if temp > 35 or temp < 5:
            risk_level = "medium" if risk_level != "high" else "high"
            indicators.append("extreme_temperature_warning")
        if temp > 40 or temp < 0:
            risk_level = "high"
            indicators.append("critical_temperature_hazard")

        # Visibility Risk
        if vis < 5:
            risk_level = "medium" if risk_level != "high" else "high"
            indicators.append("low_visibility")
        if vis < 1:
            risk_level = "high"
            indicators.append("severe_visibility_hazard")

        # UV Risk
        if uv > 6:
            risk_level = "medium" if risk_level != "high" else "high"
            indicators.append("high_uv_index")
        if uv > 8:
            risk_level = "high"
            indicators.append("extreme_uv_hazard")

        report = {
            "location": location,
            "risk_level": risk_level,
            "indicators": indicators,
            "raw_data": data
        }

        try:
            result = weather_collection.insert_one(report)
            report["_id"] = str(result.inserted_id)
        except Exception as e:
            print(f"⚠️  DB insert skipped (weather): {e}")
        return report