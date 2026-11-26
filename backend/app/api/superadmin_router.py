from fastapi import APIRouter, Depends, HTTPException, status, Request
from pydantic import BaseModel
from sqlalchemy.orm import Session
from typing import List, Dict, Any, Optional
from datetime import datetime, timezone, timedelta

from backend.app.database import get_db
from backend.app.models.company import SubscriptionPlan, Company, TelephonyConfig, SuperAdminAudit
from backend.app.models.user import User, LoginHistory
from backend.app.models.lead import Lead, LeadStage
from backend.app.models.call import CallDisposition, CallLog
from backend.app.schemas.company import (
    SubscriptionPlanCreate, SubscriptionPlanResponse,
    CompanyCreate, CompanyResponse
)
from backend.app.security.auth import get_password_hash, create_access_token
from backend.app.security.dependencies import require_roles

router = APIRouter(prefix="/superadmin", tags=["Super Admin"])

class UpdateSuperAdminNameRequest(BaseModel):
    full_name: str

@router.put("/profile/name")
def update_superadmin_name(
    req: UpdateSuperAdminNameRequest,
    admin: User = Depends(require_roles("super_admin")),
    db: Session = Depends(get_db)
):
    """
    Updates the Super Admin full name in the system.
    """
    if not req.full_name or not req.full_name.strip():
        raise HTTPException(status_code=400, detail="Name cannot be empty.")
    admin.full_name = req.full_name.strip()
    db.commit()
    return {"status": "success", "full_name": admin.full_name}

@router.get("/plans", response_model=List[SubscriptionPlanResponse])
def list_subscription_plans(
    admin: User = Depends(require_roles("super_admin")),
    db: Session = Depends(get_db)
):
    return db.query(SubscriptionPlan).all()

@router.get("/analytics")
def get_platform_analytics(
    admin: User = Depends(require_roles("super_admin")),
    db: Session = Depends(get_db)
):
    now = datetime.now(timezone.utc)
    today_start = datetime(now.year, now.month, now.day, 0, 0, 0, tzinfo=timezone.utc)

    total_companies = db.query(Company).count()
    active_companies = db.query(Company).filter(Company.is_active == True).count()
    total_agents = db.query(User).filter(User.role == "telecaller").count()
    active_agents = db.query(User).filter(User.role == "telecaller", User.is_active == True).count()
    total_leads = db.query(Lead).filter(Lead.is_deleted == False).count()

    calls_today = db.query(CallLog).filter(CallLog.started_at >= today_start).all()
    total_calls_today = len(calls_today)
    connected_calls_today = sum(1 for c in calls_today if c.status in ("connected", "completed"))
    total_talk_time_sec = sum(c.talk_time_seconds or 0 for c in calls_today)

    # 7-day trend
    trend_labels = []
    connected_trend = []
    missed_trend = []
    for i in range(6, -1, -1):
        day_date = (now - timedelta(days=i)).date()
        day_start = datetime(day_date.year, day_date.month, day_date.day, 0, 0, 0, tzinfo=timezone.utc)
        day_end = day_start + timedelta(days=1)
        
        day_calls = db.query(CallLog).filter(CallLog.started_at >= day_start, CallLog.started_at < day_end).all()
        conn = sum(1 for c in day_calls if c.status in ("connected", "completed"))
        miss = sum(1 for c in day_calls if c.status in ("missed", "no_answer", "busy", "failed"))
        
        trend_labels.append(day_date.strftime("%a"))
        connected_trend.append(conn)
        missed_trend.append(miss)

    # Plan distribution
    plans = db.query(SubscriptionPlan).all()
    plan_distribution = []
    for p in plans:
        count = db.query(Company).filter(Company.plan_id == p.id).count()
        plan_distribution.append({
            "name": p.name,
            "tier": p.tier,
            "count": count
        })

    return {
        "summary": {
            "total_companies": total_companies,
            "active_companies": active_companies,
            "total_agents": total_agents,
            "active_agents": active_agents,
            "total_leads": total_leads,
            "total_calls_today": total_calls_today,
            "connected_calls_today": connected_calls_today,
            "total_talk_time_sec": total_talk_time_sec
        },
        "weekly_chart": {
            "labels": trend_labels,
            "connected": connected_trend,
            "missed": missed_trend
        },
        "plan_distribution": plan_distribution
    }


@router.post("/plans", response_model=SubscriptionPlanResponse)
def create_subscription_plan(
    plan_in: SubscriptionPlanCreate,
    admin: User = Depends(require_roles("super_admin")),
    db: Session = Depends(get_db)
):
    existing = db.query(SubscriptionPlan).filter(SubscriptionPlan.name == plan_in.name).first()
    if existing:
        raise HTTPException(status_code=400, detail="Plan with this name already exists.")

    plan = SubscriptionPlan(
        name=plan_in.name,
        tier=plan_in.tier,
        max_employees=plan_in.max_employees,
        max_leads=plan_in.max_leads,
        recording_retention_days=plan_in.recording_retention_days,
        has_auto_dialer=plan_in.has_auto_dialer,
        has_sentiment_analysis=plan_in.has_sentiment_analysis
    )
    db.add(plan)
    db.commit()
    db.refresh(plan)
    return plan

@router.get("/companies", response_model=List[CompanyResponse])
def list_companies(
    admin: User = Depends(require_roles("super_admin")),
    db: Session = Depends(get_db)
):
    companies = db.query(Company).all()
    results = []
    for c in companies:
        user_count = db.query(User).filter(User.company_id == c.id).count()
        lead_count = db.query(Lead).filter(Lead.company_id == c.id, Lead.is_deleted == False).count()
        results.append(CompanyResponse(
            id=c.id,
            name=c.name,
            subdomain=c.subdomain,
            plan_id=c.plan_id,
            plan_name=c.plan.name if c.plan else "Standard",
            is_active=c.is_active,
            user_count=user_count,
            lead_count=lead_count,
            created_at=c.created_at
        ))
    return results

@router.post("/companies", response_model=CompanyResponse)
def onboard_client_company(
    company_in: CompanyCreate,
    admin: User = Depends(require_roles("super_admin")),
    db: Session = Depends(get_db)
):
    # Verify unique subdomain
    existing_sub = db.query(Company).filter(Company.subdomain == company_in.subdomain.strip().lower()).first()
    if existing_sub:
        raise HTTPException(status_code=400, detail="Subdomain is already taken.")

    # Verify plan exists
    plan = db.query(SubscriptionPlan).filter(SubscriptionPlan.id == company_in.plan_id).first()
    if not plan:
        raise HTTPException(status_code=404, detail="Subscription plan not found.")

    # 1. Create Company
    company = Company(
        name=company_in.name.strip(),
        subdomain=company_in.subdomain.strip().lower(),
        plan_id=plan.id,
        is_active=True
    )
    db.add(company)
    db.flush()

    # 2. Create Default Company Admin User
    admin_user = User(
        company_id=company.id,
        email=company_in.admin_email.strip().lower(),
        password_hash=get_password_hash(company_in.admin_password),
        full_name=company_in.admin_name.strip(),
        phone=company_in.admin_phone.strip(),
        role="admin",
        agent_status="offline"
    )
    db.add(admin_user)

    # 3. Create Default Telephony Config (Mock by default)
    tel_config = TelephonyConfig(
        company_id=company.id,
        provider="mock",
        virtual_number="1800-DEMO",
        recording_consent_enabled=True,
        retention_days=plan.recording_retention_days
    )
    db.add(tel_config)

    # 4. Create Standard Lead Stages
    default_stages = [
        ("New", "#3B82F6", 0, False),
        ("Interested", "#10B981", 1, False),
        ("Callback", "#F59E0B", 2, False),
        ("Not Interested", "#EF4444", 3, False),
        ("Converted", "#8B5CF6", 4, True)
    ]
    for stage_name, color, order, is_term in default_stages:
        stg = LeadStage(
            company_id=company.id,
            name=stage_name,
            color_hex=color,
            order_index=order,
            is_terminal=is_term,
            is_system=True
        )
        db.add(stg)

    # 5. Create Standard Dispositions
    default_dispositions = [
        ("CALL_DISCONNECT", "Call Disconnect", False),
        ("BUSY", "Busy", True),
        ("RINGING", "Ringing", True),
        ("CALL_BACK", "Call Back", True),
        ("NOT_INTERESTED", "Not Interested", False),
        ("OTHER", "Other", False)
    ]
    for code, label, req_fup in default_dispositions:
        disp = CallDisposition(
            company_id=company.id,
            code=code,
            label=label,
            requires_followup=req_fup
        )
        db.add(disp)

    db.commit()
    db.refresh(company)

    return CompanyResponse(
        id=company.id,
        name=company.name,
        subdomain=company.subdomain,
        plan_id=company.plan_id,
        plan_name=plan.name,
        is_active=company.is_active,
        user_count=1,
        lead_count=0,
        created_at=company.created_at
    )

@router.put("/companies/{company_id}/toggle-status")
def toggle_company_status(
    company_id: str,
    admin: User = Depends(require_roles("super_admin")),
    db: Session = Depends(get_db)
):
    company = db.query(Company).filter(Company.id == company_id).first()
    if not company:
        raise HTTPException(status_code=404, detail="Company not found.")
    company.is_active = not company.is_active
    db.commit()
    return {"status": "success", "company_id": company.id, "is_active": company.is_active}

@router.post("/impersonate-company/{company_id}")
def impersonate_company_admin(
    company_id: str,
    request: Request,
    admin: User = Depends(require_roles("super_admin")),
    db: Session = Depends(get_db)
):
    """
    Super Admin Master Access: Generates an administrative session for the specified client company.
    Grants platform owner direct access to view/manage the company's admin panel with audit logging.
    """
    company = db.query(Company).filter(Company.id == company_id).first()
    if not company:
        raise HTTPException(status_code=404, detail="Company not found.")

    target_user = db.query(User).filter(
        User.company_id == company_id,
        User.role == "admin"
    ).first()

    if not target_user:
        target_user = db.query(User).filter(User.company_id == company_id).first()

    if not target_user:
        raise HTTPException(status_code=400, detail="No users found in this company to impersonate.")

    token_data = {
        "sub": target_user.id,
        "email": target_user.email,
        "role": target_user.role,
        "company_id": company.id,
        "is_super_admin_session": True,
        "super_admin_id": admin.id,
        "super_admin_email": admin.email,
        "super_admin_name": admin.full_name
    }
    access_token = create_access_token(data=token_data)

    client_ip = request.client.host if request.client else "127.0.0.1"
    audit = SuperAdminAudit(
        super_admin_id=admin.id,
        super_admin_email=admin.email,
        target_company_id=company.id,
        target_user_id=target_user.id,
        target_user_name=target_user.full_name,
        target_role=target_user.role,
        action_type="impersonate_admin",
        description=f"Super Admin Master Session entered Admin Dashboard for company '{company.name}'",
        ip_address=client_ip
    )
    db.add(audit)
    db.commit()

    return {
        "access_token": access_token,
        "token_type": "bearer",
        "user_id": target_user.id,
        "email": target_user.email,
        "full_name": target_user.full_name,
        "role": target_user.role,
        "company_id": company.id,
        "company_name": company.name,
        "is_super_admin_session": True,
        "super_admin_email": admin.email
    }

@router.post("/impersonate-agent/{agent_id}")
def impersonate_telecaller_agent(
    agent_id: str,
    request: Request,
    admin: User = Depends(require_roles("super_admin")),
    db: Session = Depends(get_db)
):
    """
    Super Admin Master Access: Generates an agent session for the specified telecaller agent.
    Grants platform owner direct access to view and inspect the telecaller workspace.
    """
    agent = db.query(User).filter(User.id == agent_id, User.role == "telecaller").first()
    if not agent:
        raise HTTPException(status_code=404, detail="Telecaller agent not found.")

    company = db.query(Company).filter(Company.id == agent.company_id).first()

    token_data = {
        "sub": agent.id,
        "email": agent.email,
        "role": agent.role,
        "company_id": agent.company_id,
        "is_super_admin_session": True,
        "super_admin_id": admin.id,
        "super_admin_email": admin.email,
        "super_admin_name": admin.full_name
    }
    access_token = create_access_token(data=token_data)

    client_ip = request.client.host if request.client else "127.0.0.1"
    audit = SuperAdminAudit(
        super_admin_id=admin.id,
        super_admin_email=admin.email,
        target_company_id=agent.company_id,
        target_user_id=agent.id,
        target_user_name=agent.full_name,
        target_role=agent.role,
        action_type="impersonate_agent",
        description=f"Super Admin Master Session entered Agent Workspace for '{agent.full_name}' ({agent.email})",
        ip_address=client_ip
    )
    db.add(audit)
    db.commit()

    return {
        "access_token": access_token,
        "token_type": "bearer",
        "user_id": agent.id,
        "email": agent.email,
        "full_name": agent.full_name,
        "role": agent.role,
        "company_id": agent.company_id,
        "company_name": company.name if company else "Tenant",
        "is_super_admin_session": True,
        "super_admin_email": admin.email
    }

@router.get("/all-agents")
def list_all_platform_agents(
    company_id: Optional[str] = None,
    admin: User = Depends(require_roles("super_admin")),
    db: Session = Depends(get_db)
):
    """
    Returns directory of all telecaller agents across all companies with live status & workloads.
    Guarantees full visibility for Super Admin across all 10+ agents.
    """
    now = datetime.now(timezone.utc)
    today_start = datetime(now.year, now.month, now.day, 0, 0, 0, tzinfo=timezone.utc)

    query = db.query(User).filter(User.role == "telecaller")
    if company_id:
        query = query.filter(User.company_id == company_id)

    agents = query.order_by(User.full_name).all()
    results = []

    for a in agents:
        company = db.query(Company).filter(Company.id == a.company_id).first()
        leads_count = db.query(Lead).filter(Lead.assigned_to == a.id, Lead.is_deleted == False).count()
        calls_today = db.query(CallLog).filter(
            CallLog.telecaller_id == a.id,
            CallLog.started_at >= today_start
        ).all()

        total_calls = len(calls_today)
        connected_calls = sum(1 for c in calls_today if c.status in ("connected", "completed"))
        total_talk_time_sec = sum(c.talk_time_seconds or 0 for c in calls_today)

        results.append({
            "id": a.id,
            "full_name": a.full_name,
            "email": a.email,
            "phone": a.phone,
            "company_id": a.company_id,
            "company_name": company.name if company else "Unknown",
            "company_subdomain": company.subdomain if company else "",
            "role": a.role,
            "agent_status": a.agent_status,
            "is_active": a.is_active,
            "leads_count": leads_count,
            "calls_today": total_calls,
            "connected_calls": connected_calls,
            "total_talk_time_sec": total_talk_time_sec,
            "last_active": a.status_updated_at.isoformat() if a.status_updated_at else (a.created_at.isoformat() if a.created_at else None)
        })

    return results

@router.get("/audit-logs")
def get_superadmin_audit_logs(
    limit: int = 50,
    admin: User = Depends(require_roles("super_admin")),
    db: Session = Depends(get_db)
):
    """
    Returns history of Super Admin Master Access events across client tenants.
    """
    logs = db.query(SuperAdminAudit).order_by(SuperAdminAudit.created_at.desc()).limit(limit).all()
    out = []
    for l in logs:
        company = db.query(Company).filter(Company.id == l.target_company_id).first()
        out.append({
            "id": l.id,
            "super_admin_email": l.super_admin_email,
            "company_name": company.name if company else "Unknown",
            "company_id": l.target_company_id,
            "target_user_name": l.target_user_name,
            "target_role": l.target_role,
            "action_type": l.action_type,
            "description": l.description,
            "ip_address": l.ip_address,
            "created_at": l.created_at.isoformat() if l.created_at else None
        })
    return out

