from __future__ import annotations

from datetime import datetime

from fastapi.testclient import TestClient

from test_simulation_flow import _patch_backend


def test_archive_close_persists_full_incident_history(monkeypatch):
    backend = _patch_backend(monkeypatch)
    backend.simulation_service.start_simulation(
        area_id="AREA-20260318-TEST",
        radius_m=1800,
        disaster_type="Flood",
        severity="high",
        total_citizens=12,
    )

    client = TestClient(backend.main.app)
    payload = {
        "disasterType": "Flood",
        "severity": "high",
        "startedAt": datetime(2026, 3, 18, 10, 0, 0).isoformat(),
        "affectedCount": 42,
        "evacuatedCount": 18,
        "totalSosLogs": 6,
        "pendingSosCount": 2,
        "dispatchedSosCount": 4,
        "totalAidRequests": 5,
        "pendingAidCount": 1,
        "dispatchedAidCount": 4,
        "totalDispatched": 8,
        "safeCampCount": 2,
        "wasSimulation": True,
        "simulationId": backend.collections["simulation_collection"].docs[0]["id"],
        "simulatedCitizens": 12,
        "currentRisk": "high",
        "alertMessage": "Demo alert",
        "finalOutcomeSummary": "Operations stabilized and the area was closed.",
        "requestedResources": {"Water": 3, "Food": 2},
        "aiResourceSnapshot": {"ambulances": 12, "boats": 8},
        "keyActions": [
            "Simulation started for evaluator mode.",
            "Rescue team dispatched for four SOS logs.",
        ],
        "area": {
            "id": "AREA-20260318-TEST",
            "areaId": "AREA-20260318-TEST",
            "centerLat": 12.9716,
            "centerLon": 77.5946,
            "redRadiusM": 1800.0,
            "warningRadiusM": 2200.0,
            "greenRadiusM": 2600.0,
            "controllableRadiusM": 3200.0,
            "summaryLabel": "2200 m warning radius around AREA-20260318-TEST",
            "mapSummary": "Expanded demo rings were active during the archived session.",
        },
        "sosLogs": [
            {
                "id": "SOS-1",
                "status": "successful",
                "callerName": "Citizen 1",
                "phoneNumber": "9999999999",
                "address": "Main Street",
                "latitude": 12.9716,
                "longitude": 77.5946,
                "timestamp": datetime(2026, 3, 18, 10, 5, 0).isoformat(),
                "areaId": "AREA-20260318-TEST",
                "insideControllableZone": True,
            }
        ],
        "aidLogs": [
            {
                "id": "AID-1",
                "priority": "high",
                "status": "successful",
                "requesterName": "Citizen Group",
                "resources": ["Water", "Food"],
                "peopleCount": 12,
                "location": "Shelter A",
                "latitude": 12.9716,
                "longitude": 77.5946,
                "timestamp": datetime(2026, 3, 18, 10, 6, 0).isoformat(),
                "areaId": "AREA-20260318-TEST",
                "insideControllableZone": True,
            }
        ],
        "safeCamps": [
            {
                "id": "SC-1",
                "name": "Central Camp",
                "status": "active",
                "latitude": 12.9717,
                "longitude": 77.5947,
                "capacity": 150,
                "currentOccupancy": 90,
                "areaId": "AREA-20260318-TEST",
            }
        ],
        "communicationLogs": [
            {
                "id": "LOG-1",
                "type": "alert",
                "message": "Twilio alert attempted for the affected area.",
                "timestamp": datetime(2026, 3, 18, 10, 1, 0).isoformat(),
                "areaId": "AREA-20260318-TEST",
            }
        ],
        "weatherHistory": [
            {
                "timestamp": datetime(2026, 3, 18, 10, 2, 0).isoformat(),
                "riskLevel": "high",
                "condition": "Clear",
                "summary": "Threshold override forced a demo high-risk state.",
                "readings": [
                    {
                        "type": "Temperature",
                        "value": 30,
                        "unit": "C",
                        "trend": "stable",
                        "timestamp": datetime(2026, 3, 18, 10, 2, 0).isoformat(),
                    }
                ],
            }
        ],
        "decisionHistory": [
            {
                "timestamp": datetime(2026, 3, 18, 10, 0, 30).isoformat(),
                "actor": "AI Decision Agent",
                "type": "ai_suggestion",
                "summary": "Increase boats and ambulances for the flood response.",
                "resourceSnapshot": {"boats": 8, "ambulances": 12},
            }
        ],
    }

    response = client.post(
        "/admin/disaster/AREA-20260318-TEST/archive-close",
        json=payload,
    )
    assert response.status_code == 200
    body = response.json()
    assert body["area"]["isActive"] is False
    assert body["incident"]["status"] == "resolved"
    assert body["incident"]["area"]["summaryLabel"] == payload["area"]["summaryLabel"]
    assert body["incident"]["weatherHistory"][0]["riskLevel"] == "high"
    assert len(backend.collections["incident_history_collection"].docs) == 1

    active_simulation = backend.simulation_service.get_active_simulation(
        area_id="AREA-20260318-TEST"
    )
    assert active_simulation is None

    history_response = client.get("/admin/history")
    assert history_response.status_code == 200
    history_items = history_response.json()
    assert len(history_items) == 1
    assert history_items[0]["id"] == body["incident"]["id"]
