import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import pytest
import io
import json
from fastapi.testclient import TestClient
from backend.app.main import app

client = TestClient(app)

def test_bulk_upload_flow():
    # 1. Login Admin
    res_admin = client.post("/api/v1/auth/login", json={
        "email": "admin@apex.com",
        "password": "Password@123",
        "subdomain": "apex"
    })
    assert res_admin.status_code == 200
    token = res_admin.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    # 2. Download sample template (.xlsx & .csv)
    res_tpl_xlsx = client.get("/api/v1/leads/import/sample-template?format=xlsx", headers=headers)
    assert res_tpl_xlsx.status_code == 200
    assert len(res_tpl_xlsx.content) > 100

    res_tpl_csv = client.get("/api/v1/leads/import/sample-template?format=csv", headers=headers)
    assert res_tpl_csv.status_code == 200
    assert "Phone" in res_tpl_csv.text

    # 3. Preview CSV file
    csv_data = "Name,Phone,City,Source\nTest Client 1,9876543290,Pune,Website\nTest Client 2,9876543291,Goa,Campaign"
    files = {"file": ("test_leads.csv", io.BytesIO(csv_data.encode("utf-8")), "text/csv")}
    res_prev = client.post("/api/v1/leads/import/preview", headers=headers, files=files)
    assert res_prev.status_code == 200
    prev_data = res_prev.json()
    assert prev_data["total_rows"] == 2
    assert "Phone" in prev_data["headers"]
    assert prev_data["auto_mapping"]["phone"] == "Phone"

    # 4. Execute Bulk Import
    files = {"file": ("test_leads.csv", io.BytesIO(csv_data.encode("utf-8")), "text/csv")}
    mapping = {"name": "Name", "phone": "Phone", "city": "City", "source": "Source"}
    res_exec = client.post("/api/v1/leads/import/execute", headers=headers, files=files, data={
        "column_mapping_json": json.dumps(mapping),
        "duplicate_handling": "skip",
        "assignment_mode": "unassigned",
        "batch_name": "Automated Test Batch"
    })
    assert res_exec.status_code == 200
    exec_data = res_exec.json()
    assert exec_data["total_rows"] == 2
    assert exec_data["imported"] >= 1
    batch_id = exec_data["batch_id"]

    # 5. List Import History
    res_hist = client.get("/api/v1/leads/import/history", headers=headers)
    assert res_hist.status_code == 200
    history = res_hist.json()
    assert len(history) >= 1
    assert any(h["id"] == batch_id for h in history)

    # 6. Export Leads (Excel & CSV)
    res_exp_xlsx = client.get("/api/v1/leads/export/excel", headers=headers)
    assert res_exp_xlsx.status_code == 200
    assert len(res_exp_xlsx.content) > 100

    res_exp_csv = client.get("/api/v1/leads/export/csv", headers=headers)
    assert res_exp_csv.status_code == 200
    assert "Lead ID" in res_exp_csv.text

    # 7. Undo Import
    res_undo = client.post(f"/api/v1/leads/import/history/{batch_id}/undo", headers=headers)
    assert res_undo.status_code == 200
    assert res_undo.json()["status"] == "undone"

def test_weekly_analytics_dashboard():
    res_admin = client.post("/api/v1/auth/login", json={
        "email": "admin@apex.com",
        "password": "Password@123",
        "subdomain": "apex"
    })
    headers = {"Authorization": f"Bearer {res_admin.json()['access_token']}"}

    res = client.get("/api/v1/dashboard/weekly-analytics", headers=headers)
    assert res.status_code == 200
    data = res.json()
    assert "weekly_chart" in data
    assert len(data["weekly_chart"]["labels"]) == 7
    assert "stage_distribution" in data
