import pytest
from fastapi.testclient import TestClient
from backend.app.main import app
from backend.app.database import SessionLocal
from backend.app.models.user import User
from backend.app.models.company import Company, SuperAdminAudit

client = TestClient(app)

def test_minimum_10_agents_exist():
    """Verify that tenant Apex Realty Global has at least 10 active telecaller agents."""
    db = SessionLocal()
    company = db.query(Company).filter(Company.subdomain == "apex").first()
    assert company is not None
    
    agents = db.query(User).filter(
        User.company_id == company.id,
        User.role == "telecaller",
        User.is_active == True
    ).all()
    
    assert len(agents) >= 10, f"Expected at least 10 agents, found {len(agents)}"
    db.close()

def test_superadmin_all_agents_endpoint():
    """Test GET /api/v1/superadmin/all-agents returns directory of 10+ agents."""
    # 1. Login as Super Admin
    login_res = client.post("/api/v1/auth/login", json={
        "email": "superadmin@telecall.io",
        "password": "Password@123"
    })
    assert login_res.status_code == 200
    token = login_res.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    # 2. Fetch all agents
    res = client.get("/api/v1/superadmin/all-agents", headers=headers)
    assert res.status_code == 200
    data = res.json()
    assert isinstance(data, list)
    assert len(data) >= 10

    # Verify agent attributes
    first_agent = data[0]
    assert "id" in first_agent
    assert "full_name" in first_agent
    assert "email" in first_agent
    assert "agent_status" in first_agent
    assert "company_name" in first_agent

def test_superadmin_impersonate_company_admin():
    """Test Super Admin can enter Company Admin Panel with master privileges."""
    db = SessionLocal()
    company = db.query(Company).filter(Company.subdomain == "apex").first()
    company_id = company.id
    db.close()

    # Login as Super Admin
    login_res = client.post("/api/v1/auth/login", json={
        "email": "superadmin@telecall.io",
        "password": "Password@123"
    })
    super_token = login_res.json()["access_token"]
    headers = {"Authorization": f"Bearer {super_token}"}

    # Impersonate Company Admin
    imp_res = client.post(f"/api/v1/superadmin/impersonate-company/{company_id}", headers=headers)
    assert imp_res.status_code == 200
    imp_data = imp_res.json()
    assert imp_data["is_super_admin_session"] is True
    assert imp_data["role"] == "admin"
    assert imp_data["company_id"] == company_id
    admin_token = imp_data["access_token"]

    # Use impersonated token to access admin dashboard
    admin_headers = {"Authorization": f"Bearer {admin_token}"}
    profile_res = client.get("/api/v1/auth/me", headers=admin_headers)
    assert profile_res.status_code == 200
    profile = profile_res.json()
    assert profile["role"] == "admin"
    assert profile["is_super_admin_session"] is True

def test_superadmin_impersonate_agent_workspace():
    """Test Super Admin can enter any Agent Workspace with master privileges."""
    db = SessionLocal()
    agent = db.query(User).filter(User.role == "telecaller").first()
    agent_id = agent.id
    agent_name = agent.full_name
    db.close()

    # Login as Super Admin
    login_res = client.post("/api/v1/auth/login", json={
        "email": "superadmin@telecall.io",
        "password": "Password@123"
    })
    super_token = login_res.json()["access_token"]
    headers = {"Authorization": f"Bearer {super_token}"}

    # Impersonate Telecaller Agent
    imp_res = client.post(f"/api/v1/superadmin/impersonate-agent/{agent_id}", headers=headers)
    assert imp_res.status_code == 200
    imp_data = imp_res.json()
    assert imp_data["is_super_admin_session"] is True
    assert imp_data["role"] == "telecaller"
    agent_token = imp_data["access_token"]

    # Use impersonated token to access agent profile
    agent_headers = {"Authorization": f"Bearer {agent_token}"}
    profile_res = client.get("/api/v1/auth/me", headers=agent_headers)
    assert profile_res.status_code == 200
    profile = profile_res.json()
    assert profile["role"] == "telecaller"
    assert profile["full_name"] == agent_name
    assert profile["is_super_admin_session"] is True

def test_mutual_transparency_oversight_info():
    """Verify both Admin and Agent are informed of Super Admin master access."""
    # 1. Test as Admin
    admin_login = client.post("/api/v1/auth/login", json={
        "email": "admin@apex.com",
        "password": "Password@123",
        "subdomain": "apex"
    })
    assert admin_login.status_code == 200
    admin_token = admin_login.json()["access_token"]

    admin_ov = client.get("/api/v1/auth/superadmin-oversight-info", headers={"Authorization": f"Bearer {admin_token}"})
    assert admin_ov.status_code == 200
    admin_data = admin_ov.json()
    assert admin_data["master_oversight_active"] is True
    assert "superadmin@telecall.io" in admin_data["superadmin_email"]
    assert "Platform Super Admin" in admin_data["superadmin_role"]

    # 2. Test as Telecaller Agent
    agent_login = client.post("/api/v1/auth/login", json={
        "email": "priya@apex.com",
        "password": "Password@123",
        "subdomain": "apex"
    })
    assert agent_login.status_code == 200
    agent_token = agent_login.json()["access_token"]

    agent_ov = client.get("/api/v1/auth/superadmin-oversight-info", headers={"Authorization": f"Bearer {agent_token}"})
    assert agent_ov.status_code == 200
    agent_data = agent_ov.json()
    assert agent_data["master_oversight_active"] is True
    assert "transparency_notice" in agent_data

def test_superadmin_audit_logs():
    """Verify that Super Admin master sessions are recorded in audit logs."""
    login_res = client.post("/api/v1/auth/login", json={
        "email": "superadmin@telecall.io",
        "password": "Password@123"
    })
    super_token = login_res.json()["access_token"]
    headers = {"Authorization": f"Bearer {super_token}"}

    res = client.get("/api/v1/superadmin/audit-logs", headers=headers)
    assert res.status_code == 200
    logs = res.json()
    assert isinstance(logs, list)
    assert len(logs) >= 2 # From previous impersonation tests
    first_log = logs[0]
    assert "super_admin_email" in first_log
    assert "company_name" in first_log
    assert "action_type" in first_log
    assert "description" in first_log
