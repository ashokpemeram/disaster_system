from agents.weather_agent import WeatherAgent
from agents.news_agent import NewsAgent
from agents.risk_agent import RiskAgent
from agents.alert_agent import AlertAgent

class CoordinatorAgent:

    def __init__(self):
        self.weather_agent = WeatherAgent()
        self.news_agent = NewsAgent()
        self.risk_agent = RiskAgent()
        self.alert_agent = AlertAgent()

    def handle_request(self, location: str):

        weather = self.weather_agent.run(location)
        news = self.news_agent.run(location)

        risk = self.risk_agent.run(weather, news)

        if risk["overall_risk"] in ["medium", "high"]:
            alert = self.alert_agent.run(risk)
            return alert

        return {"message": "Area is safe", "risk": risk}