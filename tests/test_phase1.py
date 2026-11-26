import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import pytest
from fastapi.testclient import TestClient
from backend.app.main import app

client = TestClient(app)

def test_health_check():
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["strictly_calling_only"] is True

def test_admin_and_telecaller_login():
    # 1. Admin login
    res_admin = client.post("/api/v1/auth/login", json={
        "email": "admin@apex.com",
        "password": "Password@123",
        "subdomain": "apex"
    })
    assert res_admin.status_code == 200, res_admin.text
    admin_token = res_admin.json()["access_token"]
    assert admin_token is not None

    # 2. Telecaller login
    res_tele = client.post("/api/v1/auth/login", json={
        "email": "priya@apex.com",
        "password": "Password@123",
        "subdomain": "apex"
    })
    assert res_tele.status_code == 200, res_tele.text
    tele_token = res_tele.json()["access_token"]
    assert tele_token is not None

def test_duplicate_phone_detection():
    # Login admin
    res_admin = client.post("/api/v1/auth/login", json={
        "email": "admin@apex.com",
        "password": "Password@123",
        "subdomain": "apex"
    })
    admin_token = res_admin.json()["access_token"]
    headers = {"Authorization": f"Bearer {admin_token}"}

    # Phone +919811122233 belongs to Vikram (seeded)
    res_dup = client.post("/api/v1/leads", headers=headers, json={
        "first_name": "Duplicate",
        "phone": "+919811122233"
    })
    assert res_dup.status_code == 409, "Duplicate phone must be rejected with 409"

    # New unique phone
    import time
    unique_phone = f"+9199{int(time.time() * 1000) % 100000000:08d}"
    res_new = client.post("/api/v1/leads", headers=headers, json={
        "first_name": "Unique Customer",
        "phone": unique_phone,
        "city": "Hyderabad"
    })
    assert res_new.status_code == 200
    assert res_new.json()["first_name"] == "Unique Customer"

def test_bulk_lead_allocation_and_transfer_with_reason():
    res_admin = client.post("/api/v1/auth/login", json={
        "email": "admin@apex.com",
        "password": "Password@123",
        "subdomain": "apex"
    })
    admin_token = res_admin.json()["access_token"]
    headers = {"Authorization": f"Bearer {admin_token}"}

    # Get leads
    leads = client.get("/api/v1/leads", headers=headers).json()
    lead_ids = [l["id"] for l in leads[:2]]

    # Get telecallers
    employees = client.get("/api/v1/employees", headers=headers).json()
    emp_ids = [e["id"] for e in employees if e["role"] == "telecaller"][:2]

    # Bulk Allocate
    alloc_res = client.post("/api/v1/allocations/bulk", headers=headers, json={
        "lead_ids": lead_ids,
        "employee_ids": emp_ids,
        "mode": "equal"
    })
    assert alloc_res.status_code == 200
    assert alloc_res.json()["status"] == "success"

    # Transfer with Reason
    transfer_res = client.post("/api/v1/allocations/transfer", headers=headers, json={
        "lead_ids": [lead_ids[0]],
        "to_employee_id": emp_ids[1],
        "transfer_reason": "High priority escalation to senior agent"
    })
    assert transfer_res.status_code == 200
    assert transfer_res.json()["transfer_reason"] == "High priority escalation to senior agent"

    # Verify audit history
    hist = client.get(f"/api/v1/allocations/history/{lead_ids[0]}", headers=headers).json()
    assert len(hist) > 0
    assert any("High priority escalation" in h.get("transfer_reason", "") for h in hist)

def test_call_gate_blocking_and_disposition_unblock():
    # Login telecaller Priya
    res_tele = client.post("/api/v1/auth/login", json={
        "email": "priya@apex.com",
        "password": "Password@123",
        "subdomain": "apex"
    })
    tele_token = res_tele.json()["access_token"]
    headers = {"Authorization": f"Bearer {tele_token}"}

    # Fetch Priya's leads
    leads = client.get("/api/v1/leads", headers=headers).json()
    assert len(leads) >= 1
    lead_id = leads[0]["id"]

    # 1. Initiate 1st call
    call1 = client.post("/api/v1/calls/initiate", headers=headers, json={"lead_id": lead_id})
    assert call1.status_code == 200, call1.text
    call1_id = call1.json()["call_log_id"]

    # End 1st call (not yet disposed)
    end1 = client.post("/api/v1/calls/end", headers=headers, json={
        "call_log_id": call1_id,
        "duration_seconds": 35,
        "talk_time_seconds": 30,
        "status": "completed"
    })
    assert end1.status_code == 200

    # 2. Attempt to initiate a 2nd call BEFORE submitting disposition -> MUST BE BLOCKED!
    call2_attempt = client.post("/api/v1/calls/initiate", headers=headers, json={"lead_id": lead_id})
    assert call2_attempt.status_code == 409, "Second call must be blocked with 409 until disposition is submitted"

    # Verify Gate Status API
    gate_status = client.get("/api/v1/calls/gate-status", headers=headers).json()
    assert gate_status["is_blocked"] is True

    # 3. Submit Disposition & Notes for 1st call
    disps = client.get("/api/v1/calls/dispositions", headers=headers).json()
    disp_id = disps[0]["id"]

    disp_submit = client.post("/api/v1/calls/disposition", headers=headers, json={
        "call_log_id": call1_id,
        "disposition_id": disp_id,
        "notes": "Discussed property pricing and scheduled site visit."
    })
    assert disp_submit.status_code == 200

    # 4. Now gate status must be clear!
    gate_status_after = client.get("/api/v1/calls/gate-status", headers=headers).json()
    assert gate_status_after["is_blocked"] is False

    # 5. Initiating call now succeeds!
    call2_retry = client.post("/api/v1/calls/initiate", headers=headers, json={"lead_id": lead_id})
    assert call2_retry.status_code == 200

    # Clean up call2
    client.post("/api/v1/calls/end", headers=headers, json={
        "call_log_id": call2_retry.json()["call_log_id"],
        "duration_seconds": 10,
        "talk_time_seconds": 8,
        "status": "completed"
    })
    client.post("/api/v1/calls/disposition", headers=headers, json={
        "call_log_id": call2_retry.json()["call_log_id"],
        "disposition_id": disp_id,
        "notes": "Cleanup disposition."
    })

print("Test script ready!")
