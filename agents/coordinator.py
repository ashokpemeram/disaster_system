from agents.alert_agent import AlertAgent
from agents.news_agent import NewsAgent
from agents.risk_agent import RiskAgent
from agents.weather_agent import WeatherAgent


class CoordinatorAgent:
    def __init__(self):
        self.weather_agent = WeatherAgent()
        self.news_agent = NewsAgent()
        self.risk_agent = RiskAgent()
        self.alert_agent = AlertAgent()

    def handle_request(
        self,
        location: str,
        simulate: bool = False,
        scenario: str = None,
        area_id: str | None = None,
    ):
        if simulate:
            weather = self.weather_agent.get_mock_data(location, scenario)
            news = self.news_agent.get_mock_data(location, scenario)
        else:
            weather = self.weather_agent.run(location, area_id=area_id)
            news = self.news_agent.run(location)

        risk = self.risk_agent.run(weather, news)

        if risk["overall_risk"] in ["medium", "high"]:
            return self.alert_agent.run(risk)

        return {"message": "Area is safe", "risk": risk}
