from tools.news_tool import fetch_news
from db import news_collection

class NewsAgent:

    def run(self, location: str):
        data = fetch_news(location)

        events = []
        risk_score = 0

        for article in data.get("articles", []):
            title = article["title"].lower()
            if any(word in title for word in ["flood", "earthquake", "cyclone"]):
                events.append(title)
                risk_score += 1

        risk_level = "low"
        if risk_score >= 3:
            risk_level = "high"
        elif risk_score >= 1:
            risk_level = "medium"

        report = {
            "location": location,
            "events": events,
            "risk_level": risk_level
        }

        news_collection.insert_one(report)
        return report