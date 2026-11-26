import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import pytest
from fastapi.testclient import TestClient
from backend.app.main import app

client = TestClient(app)

def test_autodialer_session_flow():
    # Login Priya (Telecaller)
    res_tele = client.post("/api/v1/auth/login", json={
        "email": "priya@apex.com",
        "password": "Password@123",
        "subdomain": "apex"
    })
    assert res_tele.status_code == 200
    token = res_tele.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    # Fetch assigned leads
    leads_res = client.get("/api/v1/leads", headers=headers)
    assert leads_res.status_code == 200
    leads = leads_res.json()
    assert len(leads) >= 1
    custom_ids = [l["id"] for l in leads[:3]]

    # 1. Start Auto-Dialer session in preview mode
    start_res = client.post("/api/v1/autodialer/start", headers=headers, json={
        "name": "Sprint Calling Batch",
        "mode": "preview",
        "custom_lead_ids": custom_ids,
        "countdown_seconds": 5
    })
    assert start_res.status_code == 200
    session_data = start_res.json()
    assert session_data["status"] == "running"
    assert session_data["total_leads"] == len(custom_ids)
    session_id = session_data["session_id"]

    # 2. Check session status
    get_res = client.get(f"/api/v1/autodialer/session/{session_id}", headers=headers)
    assert get_res.status_code == 200
    current_session = get_res.json()
    assert current_session["current_lead"] is not None
    assert current_session["mode"] == "preview"

    # 3. Pause and Resume session
    pause_res = client.post(f"/api/v1/autodialer/session/{session_id}/pause", headers=headers)
    assert pause_res.status_code == 200
    assert pause_res.json()["status"] == "paused"

    resume_res = client.post(f"/api/v1/autodialer/session/{session_id}/resume", headers=headers)
    assert resume_res.status_code == 200
    assert resume_res.json()["status"] == "running"

    # 4. Skip lead to advance queue
    skip_res = client.post(f"/api/v1/autodialer/session/{session_id}/skip", headers=headers)
    assert skip_res.status_code == 200
    assert skip_res.json()["skipped_count"] >= 1

    # 5. Stop session
    stop_res = client.post(f"/api/v1/autodialer/session/{session_id}/stop", headers=headers)
    assert stop_res.status_code == 200
    assert stop_res.json()["status"] == "stopped"

def test_realtime_dashboard():
    # Login Admin
    res_admin = client.post("/api/v1/auth/login", json={
        "email": "admin@apex.com",
        "password": "Password@123",
        "subdomain": "apex"
    })
    assert res_admin.status_code == 200
    headers = {"Authorization": f"Bearer {res_admin.json()['access_token']}"}

    # Fetch Realtime Dashboard Metrics
    res = client.get("/api/v1/dashboard/realtime", headers=headers)
    assert res.status_code == 200
    data = res.json()
    
    assert "summary" in data
    assert "agent_counts" in data
    assert "agents" in data
    summary = data["summary"]
    assert "total_calls_today" in summary
    assert "connected_calls" in summary
    assert "average_call_duration_sec" in summary
    assert "conversion_rate_percentage" in summary
    assert "idle" in data["agent_counts"]

def test_performance_dashboard():
    # Login Admin
    res_admin = client.post("/api/v1/auth/login", json={
        "email": "admin@apex.com",
        "password": "Password@123",
        "subdomain": "apex"
    })
    headers = {"Authorization": f"Bearer {res_admin.json()['access_token']}"}

    # Fetch Performance stats
    res = client.get("/api/v1/dashboard/performance", headers=headers)
    assert res.status_code == 200
    perf = res.json()
    assert isinstance(perf, list)
    if len(perf) > 0:
        agent = perf[0]
        assert "agent_id" in agent
        assert "agent_name" in agent
        assert "agent_status" in agent
        assert "today_calls_count" in agent
        assert "avg_gap_between_calls_sec" in agent

def test_reports_calls_and_exports():
    # Login Admin
    res_admin = client.post("/api/v1/auth/login", json={
        "email": "admin@apex.com",
        "password": "Password@123",
        "subdomain": "apex"
    })
    headers = {"Authorization": f"Bearer {res_admin.json()['access_token']}"}

    # 1. Fetch Paginated Call Report
    res = client.get("/api/v1/reports/calls?limit=10&offset=0", headers=headers)
    assert res.status_code == 200
    report = res.json()
    assert isinstance(report, list)

    # 2. Export CSV
    csv_res = client.get("/api/v1/reports/calls/export/csv", headers=headers)
    assert csv_res.status_code == 200
    assert "text/csv" in csv_res.headers["content-type"]
    assert "Call ID" in csv_res.text or "call_id" in csv_res.text.lower() or "Customer" in csv_res.text

    # 3. Export Excel
    excel_res = client.get("/api/v1/reports/calls/export/excel", headers=headers)
    assert excel_res.status_code == 200
    assert "spreadsheetml" in excel_res.headers["content-type"]
    assert len(excel_res.content) > 100
