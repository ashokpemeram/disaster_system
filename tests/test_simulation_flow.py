from __future__ import annotations

from copy import deepcopy
from datetime import datetime
from types import SimpleNamespace
import importlib

from fastapi.testclient import TestClient
from pymongo import ReturnDocument


class FakeCursor(list):
    def sort(self, key, direction):
        reverse = direction == -1
        return FakeCursor(sorted(self, key=lambda doc: doc.get(key), reverse=reverse))

    def limit(self, count):
        return FakeCursor(self[:count])


class FakeCollection:
    def __init__(self, docs=None):
        self.docs = []
        self._counter = 0
        for doc in docs or []:
            self.insert_one(doc)

    def _clone(self, value):
        return deepcopy(value)

    def _project(self, doc, projection):
        if not projection:
            return self._clone(doc)

        included = [key for key, enabled in projection.items() if enabled]
        projected = {key: self._clone(doc[key]) for key in included if key in doc}
        if projection.get("_id", 1) and "_id" in doc:
            projected["_id"] = doc["_id"]
        return projected

    def _matches(self, doc, query):
        if not query:
            return True

        for key, expected in query.items():
            if key == "$or":
                if not any(self._matches(doc, branch) for branch in expected):
                    return False
                continue

            exists = key in doc
            value = doc.get(key)
            if isinstance(expected, dict):
                for operator, operand in expected.items():
                    if operator == "$ne":
                        if value == operand:
                            return False
                    elif operator == "$exists":
                        if bool(operand) != exists:
                            return False
                    else:
                        raise AssertionError(f"Unsupported query operator: {operator}")
                continue

            if value != expected:
                return False

        return True

    def _apply_update(self, doc, update):
        for key, payload in update.items():
            if key == "$set":
                for field, value in payload.items():
                    doc[field] = self._clone(value)
            else:
                raise AssertionError(f"Unsupported update operator: {key}")

    def insert_one(self, doc):
        record = self._clone(doc)
        record.setdefault("_id", f"fake-{self._counter}")
        self._counter += 1
        self.docs.append(record)
        return SimpleNamespace(inserted_id=record["_id"])

    def find(self, query=None, projection=None):
        items = [
            self._project(doc, projection)
            for doc in self.docs
            if self._matches(doc, query or {})
        ]
        return FakeCursor(items)

    def find_one(self, query=None, projection=None, sort=None):
        items = list(self.find(query, projection))
        if sort:
            for key, direction in reversed(sort):
                items.sort(key=lambda doc: doc.get(key), reverse=direction == -1)
        return self._clone(items[0]) if items else None

    def update_one(self, query, update, upsert=False):
        for doc in self.docs:
            if self._matches(doc, query):
                self._apply_update(doc, update)
                return SimpleNamespace(matched_count=1, modified_count=1)

        if upsert:
            new_doc = {}
            for key, value in query.items():
                if not key.startswith("$") and not isinstance(value, dict):
                    new_doc[key] = self._clone(value)
            self._apply_update(new_doc, update)
            self.insert_one(new_doc)
            return SimpleNamespace(matched_count=0, modified_count=1)

        return SimpleNamespace(matched_count=0, modified_count=0)

    def find_one_and_update(self, query, update, return_document=None):
        for doc in self.docs:
            if self._matches(doc, query):
                before = self._clone(doc)
                self._apply_update(doc, update)
                if return_document == ReturnDocument.AFTER:
                    return self._clone(doc)
                return before
        return None


def _seed_area():
    return {
        "id": "AREA-20260318-TEST",
        "centerLat": 12.9716,
        "centerLon": 77.5946,
        "redRadiusM": 300.0,
        "warningRadiusM": 600.0,
        "greenRadiusM": 900.0,
        "controllableRadiusM": 1200.0,
        "createdAt": datetime(2026, 3, 18, 12, 0, 0).isoformat(),
        "isActive": True,
    }


def _weather_payload():
    return {
        "current": {
            "temp_c": 30.0,
            "wind_kph": 10.0,
            "condition": {"text": "Clear"},
            "precip_mm": 0.0,
            "vis_km": 10.0,
            "uv": 1.0,
            "humidity": 55,
        }
    }


def _stub_client():
    class _Completions:
        def create(self, *args, **kwargs):
            return SimpleNamespace(
                choices=[SimpleNamespace(message=SimpleNamespace(content="Demo alert"))]
            )

    return SimpleNamespace(chat=SimpleNamespace(completions=_Completions()))


def _patch_backend(monkeypatch):
    main = importlib.import_module("main")
    db_module = importlib.import_module("db")
    admin_router_module = importlib.import_module("routers.admin")
    area_service = importlib.import_module("services.area_service")
    simulation_service = importlib.import_module("services.simulation_service")
    weather_agent_module = importlib.import_module("agents.weather_agent")
    news_agent_module = importlib.import_module("agents.news_agent")
    risk_agent_module = importlib.import_module("agents.risk_agent")
    alert_agent_module = importlib.import_module("agents.alert_agent")

    collections = {
        "area_collection": FakeCollection([_seed_area()]),
        "simulation_collection": FakeCollection(),
        "weather_collection": FakeCollection(),
        "news_collection": FakeCollection(),
        "risk_collection": FakeCollection(),
        "alert_collection": FakeCollection(),
        "aid_request_collection": FakeCollection(),
        "sos_request_collection": FakeCollection(),
        "incident_history_collection": FakeCollection(),
    }

    modules_to_patch = [
        db_module,
        main,
        admin_router_module,
        area_service,
        simulation_service,
        weather_agent_module,
        news_agent_module,
        risk_agent_module,
        alert_agent_module,
    ]
    for module in modules_to_patch:
        for attr_name, collection in collections.items():
            if hasattr(module, attr_name):
                monkeypatch.setattr(module, attr_name, collection)
        if hasattr(module, "mongo_available"):
            monkeypatch.setattr(module, "mongo_available", True)

    sms_calls = []
    monkeypatch.setattr(weather_agent_module, "fetch_weather", lambda location: _weather_payload())
    monkeypatch.setattr(news_agent_module, "fetch_news", lambda location: {"articles": []})
    monkeypatch.setattr(alert_agent_module, "client", _stub_client())
    monkeypatch.setattr(
        alert_agent_module,
        "send_sms",
        lambda recipient, message: sms_calls.append((recipient, message)),
    )
    monkeypatch.setenv("RECIPIENT_PHONE_NUMBER", "+15550000000")

    return SimpleNamespace(
        main=main,
        simulation_service=simulation_service,
        weather_agent_module=weather_agent_module,
        collections=collections,
        sms_calls=sms_calls,
    )


def test_simulation_start_live_weather_assess_and_stop(monkeypatch):
    backend = _patch_backend(monkeypatch)
    client = TestClient(backend.main.app)

    start_response = client.post(
        "/simulation/start",
        json={
            "areaId": "AREA-20260318-TEST",
            "latitude": 12.9716,
            "longitude": 77.5946,
            "radiusM": 1800,
            "disasterType": "Flood",
            "severity": "high",
            "triggerAssessment": True,
            "totalCitizens": 20,
            "intervalSeconds": 2,
        },
    )
    assert start_response.status_code == 200
    start_body = start_response.json()
    assert start_body["session"]["isActive"] is True
    assert start_body["assessment"]["risk"]["overall_risk"] == "high"
    assert start_body["area"]["redRadiusM"] == 1800
    assert len(backend.collections["simulation_collection"].docs) == 1
    assert len(backend.sms_calls) == 1

    live_weather = client.get(
        "/live-weather/AREA-20260318-TEST",
        params={"lat": 12.9716, "lon": 77.5946},
    )
    assert live_weather.status_code == 200
    assert live_weather.json()["risk_level"] == "high"

    assess_response = client.post(
        "/assess",
        json={"location": "12.9716,77.5946"},
    )
    assert assess_response.status_code == 200
    assert assess_response.json()["risk"]["overall_risk"] == "high"
    assert len(backend.sms_calls) == 1

    active_response = client.get(
        "/simulation/active",
        params={"area_id": "AREA-20260318-TEST"},
    )
    assert active_response.status_code == 200
    assert active_response.json()["session"]["id"] == start_body["session"]["id"]

    stop_response = client.post(
        "/simulation/stop",
        json={"areaId": "AREA-20260318-TEST"},
    )
    assert stop_response.status_code == 200
    stop_body = stop_response.json()
    assert stop_body["session"]["isActive"] is False
    assert stop_body["area"]["redRadiusM"] == 300.0

    restored_assess = client.post(
        "/assess",
        json={"location": "12.9716,77.5946"},
    )
    assert restored_assess.status_code == 200
    assert restored_assess.json()["risk"]["overall_risk"] == "low"

    restored_live_weather = client.get(
        "/live-weather/AREA-20260318-TEST",
        params={"lat": 12.9716, "lon": 77.5946},
    )
    assert restored_live_weather.status_code == 200
    assert restored_live_weather.json()["risk_level"] == "low"


def test_medium_threshold_override_is_used_and_restored(monkeypatch):
    backend = _patch_backend(monkeypatch)
    session, _area = backend.simulation_service.start_simulation(
        area_id="AREA-20260318-TEST",
        radius_m=1200,
        disaster_type="Cyclone",
        severity="medium",
    )

    medium_report = backend.weather_agent_module.WeatherAgent().run(
        "12.9716,77.5946",
        area_id="AREA-20260318-TEST",
    )
    assert session["thresholdProfile"]["temperature_c"]["high_medium"] == -100.0
    assert medium_report["risk_level"] == "medium"

    backend.simulation_service.stop_simulation(area_id="AREA-20260318-TEST")
    restored_report = backend.weather_agent_module.WeatherAgent().run(
        "12.9716,77.5946",
        area_id="AREA-20260318-TEST",
    )
    assert restored_report["risk_level"] == "low"
