import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import pytest
from fastapi.testclient import TestClient
from backend.app.main import app

client = TestClient(app)

def test_telephony_config_get_and_update():
    # Login Admin
    res_admin = client.post("/api/v1/auth/login", json={
        "email": "admin@apex.com",
        "password": "Password@123",
        "subdomain": "apex"
    })
    admin_token = res_admin.json()["access_token"]
    headers = {"Authorization": f"Bearer {admin_token}"}

    # 1. Get telephony config
    res_get = client.get("/api/v1/telephony/config", headers=headers)
    assert res_get.status_code == 200
    cfg = res_get.json()
    assert "provider" in cfg
    assert "recording_consent_enabled" in cfg

    # 2. Update telephony config (e.g. switch to Exotel, customize virtual number & retention)
    res_put = client.put("/api/v1/telephony/config", headers=headers, json={
        "provider": "exotel",
        "virtual_number": "+918000998877",
        "account_sid": "exo_acc_12345",
        "api_key": "exo_key_67890",
        "api_token": "exo_tok_abcdef",
        "recording_consent_enabled": True,
        "consent_announcement_text": "Call is recorded for regulatory compliance.",
        "retention_days": 90,
        "is_active": True
    })
    assert res_put.status_code == 200
    updated = res_put.json()
    assert updated["provider"] == "exotel"
    assert updated["virtual_number"] == "+918000998877"
    assert updated["retention_days"] == 90
    assert updated["consent_announcement_text"] == "Call is recorded for regulatory compliance."

def test_telephony_webhook_call_completion():
    # Login Priya
    res_tele = client.post("/api/v1/auth/login", json={
        "email": "priya@apex.com",
        "password": "Password@123",
        "subdomain": "apex"
    })
    tele_token = res_tele.json()["access_token"]
    headers = {"Authorization": f"Bearer {tele_token}"}

    # Fetch Priya's leads
    leads = client.get("/api/v1/leads", headers=headers).json()
    lead_id = leads[0]["id"]

    # 1. Initiate call
    call_init = client.post("/api/v1/calls/initiate", headers=headers, json={"lead_id": lead_id})
    assert call_init.status_code == 200
    call_sid = call_init.json()["provider_sid"]
    call_log_id = call_init.json()["call_log_id"]

    # 2. Simulate Telephony Provider Webhook (Exotel / Twilio status callback)
    webhook_res = client.post(
        "/api/v1/telephony/webhook/exotel",
        data={
            "CallSid": call_sid,
            "Status": "completed",
            "Duration": "92",
            "RecordingUrl": "https://s3.amazonaws.com/telephony-recordings/call_92s.mp3"
        }
    )
    assert webhook_res.status_code == 200
    assert webhook_res.json()["status"] == "processed"

    # 3. Clean up disposition so agent remains unblocked
    disps = client.get("/api/v1/calls/dispositions", headers=headers).json()
    client.post("/api/v1/calls/disposition", headers=headers, json={
        "call_log_id": call_log_id,
        "disposition_id": disps[0]["id"],
        "notes": "Telephony webhook test call completed."
    })

def test_missed_call_triggers_callback_and_in_app_notification():
    # Login Priya
    res_tele = client.post("/api/v1/auth/login", json={
        "email": "priya@apex.com",
        "password": "Password@123",
        "subdomain": "apex"
    })
    tele_token = res_tele.json()["access_token"]
    headers = {"Authorization": f"Bearer {tele_token}"}

    leads = client.get("/api/v1/leads", headers=headers).json()
    lead_id = leads[0]["id"]

    # 1. Initiate call
    call_init = client.post("/api/v1/calls/initiate", headers=headers, json={"lead_id": lead_id})
    call_sid = call_init.json()["provider_sid"]
    call_log_id = call_init.json()["call_log_id"]

    # 2. Simulate Inbound Missed Call Webhook
    webhook_res = client.post(
        "/api/v1/telephony/webhook/exotel",
        data={
            "CallSid": call_sid,
            "Status": "no-answer",
            "Duration": "0"
        }
    )
    assert webhook_res.status_code == 200

    # 3. Verify in-app notification generated for Priya
    notifs = client.get("/api/v1/notifications?unread_only=true", headers=headers).json()
    assert len(notifs) > 0
    missed_notif = next((n for n in notifs if n["type"] == "missed_call"), None)
    assert missed_notif is not None, "Must generate missed_call in-app alert"
    assert "Missed Call" in missed_notif["title"]

    # Clean up call gate
    disps = client.get("/api/v1/calls/dispositions", headers=headers).json()
    client.post("/api/v1/calls/disposition", headers=headers, json={
        "call_log_id": call_log_id,
        "disposition_id": disps[0]["id"],
        "notes": "Customer did not answer."
    })

def test_in_app_notification_lifecycle_and_unread_counts():
    # Login Admin
    res_admin = client.post("/api/v1/auth/login", json={
        "email": "admin@apex.com",
        "password": "Password@123",
        "subdomain": "apex"
    })
    admin_token = res_admin.json()["access_token"]
    admin_headers = {"Authorization": f"Bearer {admin_token}"}

    # Login Priya
    res_tele = client.post("/api/v1/auth/login", json={
        "email": "priya@apex.com",
        "password": "Password@123",
        "subdomain": "apex"
    })
    tele_token = res_tele.json()["access_token"]
    tele_headers = {"Authorization": f"Bearer {tele_token}"}

    # 1. Admin assigns lead to Priya -> generates lead_assigned notification
    leads = client.get("/api/v1/leads", headers=admin_headers).json()
    employees = client.get("/api/v1/employees", headers=admin_headers).json()
    priya = next(e for e in employees if e["email"] == "priya@apex.com")

    client.post(f"/api/v1/allocations/single/{leads[0]['id']}", headers=admin_headers, json={
        "employee_id": priya["id"]
    })

    # 2. Check unread count for Priya
    unread_res = client.get("/api/v1/notifications/unread-count", headers=tele_headers).json()
    assert unread_res["unread_count"] >= 1

    # 3. Priya fetches notifications
    notif_list = client.get("/api/v1/notifications", headers=tele_headers).json()
    assert len(notif_list) >= 1
    lead_assigned_notif = next(n for n in notif_list if n["type"] == "lead_assigned")
    assert lead_assigned_notif is not None

    # 4. Mark single read
    mark_res = client.put(f"/api/v1/notifications/{lead_assigned_notif['id']}/read", headers=tele_headers)
    assert mark_res.status_code == 200

    # 5. Mark all read
    read_all_res = client.post("/api/v1/notifications/read-all", headers=tele_headers)
    assert read_all_res.status_code == 200

    # 6. Verify unread count is now 0
    unread_after = client.get("/api/v1/notifications/unread-count", headers=tele_headers).json()
    assert unread_after["unread_count"] == 0

def test_admin_overdue_followups_alert():
    # Login Admin
    res_admin = client.post("/api/v1/auth/login", json={
        "email": "admin@apex.com",
        "password": "Password@123",
        "subdomain": "apex"
    })
    admin_token = res_admin.json()["access_token"]
    admin_headers = {"Authorization": f"Bearer {admin_token}"}

    # Check alerts (seeded data has Ananya with overdue follow-up)
    alert_check = client.post("/api/v1/notifications/check-admin-alerts", headers=admin_headers).json()
    assert alert_check["status"] == "success"
    assert alert_check["overdue_count"] >= 1

    # Fetch admin notifications
    admin_notifs = client.get("/api/v1/notifications", headers=admin_headers).json()
    overdue_notif = next((n for n in admin_notifs if n["type"] == "admin_alert"), None)
    assert overdue_notif is not None, "Admin must receive overdue follow-up alert"
    assert "Overdue Follow-ups" in overdue_notif["title"]

print("Phase 2 tests ready!")
