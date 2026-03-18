from tools.weather_tool import fetch_weather

from db import weather_collection
from services.simulation_service import resolve_weather_threshold_profile


def _promote_risk(current_level: str, candidate_level: str) -> str:
    order = {"low": 0, "medium": 1, "high": 2}
    if order.get(candidate_level, 0) > order.get(current_level, 0):
        return candidate_level
    return current_level


class WeatherAgent:
    def run(self, location: str, area_id: str | None = None):
        data = fetch_weather(location)
        print("Weather API Response:", data)

        thresholds, active_simulation = resolve_weather_threshold_profile(
            area_id=area_id,
            location=location,
        )
        indicators = []
        risk_level = "low"

        temp = data["current"]["temp_c"]
        wind = data["current"]["wind_kph"]
        condition = data["current"]["condition"]["text"].lower()
        precip = data["current"].get("precip_mm", 0)
        vis = data["current"].get("vis_km", 0)
        uv = data["current"].get("uv", 0)

        if wind > thresholds["wind_kph"]["medium"]:
            risk_level = _promote_risk(risk_level, "medium")
            indicators.append("heavy_wind")
        if wind > thresholds["wind_kph"]["high"]:
            risk_level = _promote_risk(risk_level, "high")
            indicators.append("storm_level_wind")

        if "rain" in condition or precip > thresholds["precip_mm"]["medium"]:
            risk_level = _promote_risk(risk_level, "medium")
            indicators.append("heavy_rain")
        if precip > thresholds["precip_mm"]["high"]:
            risk_level = _promote_risk(risk_level, "high")
            indicators.append("heavy_precipitation")

        if (
            temp > thresholds["temperature_c"]["high_medium"]
            or temp < thresholds["temperature_c"]["low_medium"]
        ):
            risk_level = _promote_risk(risk_level, "medium")
            indicators.append("extreme_temperature_warning")
        if (
            temp > thresholds["temperature_c"]["high_high"]
            or temp < thresholds["temperature_c"]["low_high"]
        ):
            risk_level = _promote_risk(risk_level, "high")
            indicators.append("critical_temperature_hazard")

        if vis < thresholds["visibility_km"]["medium"]:
            risk_level = _promote_risk(risk_level, "medium")
            indicators.append("low_visibility")
        if vis < thresholds["visibility_km"]["high"]:
            risk_level = _promote_risk(risk_level, "high")
            indicators.append("severe_visibility_hazard")

        if uv > thresholds["uv_index"]["medium"]:
            risk_level = _promote_risk(risk_level, "medium")
            indicators.append("high_uv_index")
        if uv > thresholds["uv_index"]["high"]:
            risk_level = _promote_risk(risk_level, "high")
            indicators.append("extreme_uv_hazard")

        report = {
            "location": location,
            "areaId": area_id or (active_simulation or {}).get("areaId"),
            "risk_level": risk_level,
            "indicators": indicators,
            "raw_data": data,
            "threshold_profile": thresholds,
            "simulationId": (active_simulation or {}).get("id"),
        }

        try:
            result = weather_collection.insert_one(report)
            report["_id"] = str(result.inserted_id)
        except Exception as e:
            print(f"DB insert skipped (weather): {e}")
        return report

    def get_mock_data(self, location: str, scenario: str = None):
        """Returns high-risk weather data for the legacy mock simulation flow."""
        data = {
            "current": {
                "temp_c": 42.0,
                "wind_kph": 95.0,
                "condition": {"text": "Storm"},
                "precip_mm": 15.0,
                "vis_km": 0.5,
                "uv": 10.0,
            }
        }
        report = {
            "location": location,
            "risk_level": "high",
            "indicators": [
                "storm_level_wind",
                "heavy_precipitation",
                "critical_temperature_hazard",
                "severe_visibility_hazard",
                "extreme_uv_hazard",
            ],
            "raw_data": data,
            "areaId": None,
            "simulationId": None,
        }

        try:
            result = weather_collection.insert_one(report)
            report["_id"] = str(result.inserted_id)
        except Exception as e:
            print(f"DB insert skipped (weather simulation): {e}")

        return report
