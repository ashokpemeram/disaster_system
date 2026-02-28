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

        if "rain" in condition or wind > 50:
            risk_level = "medium"
            indicators.append("heavy_rain_or_wind")

        if wind > 80:
            risk_level = "high"
            indicators.append("storm_level_wind")

        report = {
            "location": location,
            "risk_level": risk_level,
            "indicators": indicators,
            "raw_data": data
        }

        result = weather_collection.insert_one(report)
        report["_id"] = str(result.inserted_id)
        return report