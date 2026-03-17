from db import risk_collection

class RiskAgent:

    def run(self, weather_report, news_report, simulation_area=None):
        levels = [weather_report["risk_level"], news_report["risk_level"]]
        
        # Pull risk from simulation if exists
        sim_risk = simulation_area.get("severity", "low") if simulation_area else "low"
        levels.append(sim_risk)

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
            "news": news_report,
            "simulated": simulation_area is not None,
            "disaster_type": simulation_area.get("type") if simulation_area else None
        }

        try:
            risk_collection.insert_one(assessment)
        except Exception as e:
            print(f"⚠️  DB insert skipped (risk): {e}")
        return assessment