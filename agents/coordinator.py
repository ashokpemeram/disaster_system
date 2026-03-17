from agents.weather_agent import WeatherAgent
from agents.news_agent import NewsAgent
from agents.risk_agent import RiskAgent
from agents.alert_agent import AlertAgent
from db import area_collection
from utils import haversine_distance_m

class CoordinatorAgent:

    def __init__(self):
        self.weather_agent = WeatherAgent()
        self.news_agent = NewsAgent()
        self.risk_agent = RiskAgent()
        self.alert_agent = AlertAgent()

    def handle_request(self, location: str, lat: float = None, lon: float = None):
        weather = self.weather_agent.run(location)
        news = self.news_agent.run(location)

        # Check for active simulation areas
        simulation_area = None
        if lat is not None and lon is not None:
            active_areas = area_collection.find({"isActive": True})
            for area in active_areas:
                dist = haversine_distance_m(lat, lon, area["centerLat"], area["centerLon"])
                if dist <= area.get("controllableRadiusM", 5000):
                    simulation_area = area
                    break

        risk = self.risk_agent.run(weather, news, simulation_area=simulation_area)

        if risk["overall_risk"] in ["medium", "high"]:
            alert = self.alert_agent.run(risk)
            return alert

        return {"message": "Area is safe", "risk": risk}