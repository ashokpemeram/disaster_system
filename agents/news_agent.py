from tools.news_tool import fetch_news
from db import news_collection

_NEWS_MEDIUM_MATCH_COUNT = 1
_NEWS_HIGH_MATCH_COUNT = 2
_NEWS_RISK_KEYWORDS = ("flood", "earthquake", "cyclone")


class NewsAgent:

    def run(self, location: str):
        data = fetch_news(location)

        events = []
        risk_score = 0

        for article in data.get("articles", []):
            title = article["title"].lower()
            if any(word in title for word in _NEWS_RISK_KEYWORDS):
                events.append(title)
                risk_score += 1

        risk_level = "low"
        if risk_score >= _NEWS_HIGH_MATCH_COUNT:
            risk_level = "high"
        elif risk_score >= _NEWS_MEDIUM_MATCH_COUNT:
            risk_level = "medium"

        report = {
            "location": location,
            "events": events,
            "risk_level": risk_level
        }

        try:
            news_collection.insert_one(report)
        except Exception as e:
            print(f"⚠️  DB insert skipped (news): {e}")
        return report

    def get_mock_data(self, location: str, scenario: str = None):
        """Returns high-risk news data for simulation."""
        report = {
            "location": location,
            "events": ["Massive earthquake reported", "Tsunami warning issued", "Severe flooding in city center"],
            "risk_level": "high"
        }
        try:
            news_collection.insert_one(report)
        except Exception as e:
            print(f"⚠️  DB insert skipped (news simulation): {e}")
        return report
