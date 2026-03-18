import logging
import os
from types import SimpleNamespace

from dotenv import load_dotenv
from pymongo import MongoClient


load_dotenv()

logger = logging.getLogger(__name__)

_MONGO_URI = os.getenv("MONGO_URI")
_DB_NAME = "disaster_system"
_SERVER_SELECTION_TIMEOUT_MS = 5000


class DatabaseUnavailableError(RuntimeError):
    """Raised when MongoDB is unavailable for an operation."""


class _FakeCursor(list):
    def sort(self, *args, **kwargs):
        return self

    def limit(self, *args, **kwargs):
        return self


class _FakeCollection:
    """A no-op collection stub used when MongoDB is unavailable."""

    def insert_one(self, doc):
        return SimpleNamespace(inserted_id="offline")

    def update_one(self, *args, **kwargs):
        return SimpleNamespace(matched_count=0, modified_count=0)

    def find_one_and_update(self, *args, **kwargs):
        return None

    def find(self, *args, **kwargs):
        return _FakeCursor()

    def find_one(self, *args, **kwargs):
        return None


client = None
db = None
_mongo_available = False

if _MONGO_URI:
    try:
        client = MongoClient(
            _MONGO_URI,
            serverSelectionTimeoutMS=_SERVER_SELECTION_TIMEOUT_MS,
        )
        client.admin.command("ping")
        db = client[_DB_NAME]
        _mongo_available = True
        logger.info("MongoDB sync client connected successfully.")
    except Exception as exc:
        logger.warning("MongoDB sync client unavailable: %s", exc)
else:
    logger.warning("MONGO_URI is not configured.")


def _get_collection(name: str):
    if _mongo_available and db is not None:
        return db[name]
    return _FakeCollection()


weather_collection = _get_collection("weather_reports")
news_collection = _get_collection("news_reports")
risk_collection = _get_collection("risk_assessments")
alert_collection = _get_collection("alerts")
aid_request_collection = _get_collection("aid_requests")
area_collection = _get_collection("disaster_areas")
sos_request_collection = _get_collection("sos_requests")
simulation_collection = _get_collection("simulation_sessions")
incident_history_collection = _get_collection("incident_history")

mongo_available = _mongo_available
