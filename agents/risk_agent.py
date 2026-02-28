from db import risk_collection

class RiskAgent:

    def run(self, weather_report, news_report):
        levels = [weather_report["risk_level"], news_report["risk_level"]]

        if "high" in levels:
            overall = "high"
        elif "medium" in levels:
            overall = "medium"
        else:
            overall = "low"

        assessment = {
            "location": weather_report["location"],
            "overall_risk": overall,
            "weather": weather_report,
            "news": news_report
        }

        risk_collection.insert_one(assessment)
        return assessment