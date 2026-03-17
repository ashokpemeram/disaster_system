import os
from pymongo import MongoClient
from dotenv import load_dotenv

load_dotenv()

try:
    client = MongoClient(os.getenv("MONGO_URI"), serverSelectionTimeoutMS=5000)
    # Trigger a quick connection check
    client.admin.command("ping")
    db = client["disaster_system"]
    _mongo_available = True
    print("✅ MongoDB connected successfully.")
except Exception as e:
    print(f"⚠️  MongoDB not available: {e}. DB operations will be skipped.")
    client = None
    db = None
    _mongo_available = False


class _FakeCollection:
    """A no-op collection stub used when MongoDB is unavailable."""
    def insert_one(self, doc):
        class _FakeResult:
            inserted_id = "offline"
        return _FakeResult()

    def update_one(self, *args, **kwargs):
        pass

    def find(self, *args, **kwargs):
        return []

    def find_one(self, *args, **kwargs):
        return None


def _get_collection(name: str):
    if _mongo_available and db is not None:
        return db[name]
    return _FakeCollection()


weather_collection = _get_collection("weather_reports")
news_collection = _get_collection("news_reports")
risk_collection = _get_collection("risk_assessments")
alert_collection = _get_collection("alerts")