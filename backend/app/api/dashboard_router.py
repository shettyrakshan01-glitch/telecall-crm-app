from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy import func, and_, desc
from typing import Dict, Any, List
from datetime import datetime, timezone, timedelta, date

from backend.app.database import get_db
from backend.app.models.user import User, TelecallerShift, BreakLog
from backend.app.models.call import CallLog, CallDisposition
from backend.app.models.lead import Lead, LeadStage
from backend.app.models.followup import FollowUp
from backend.app.security.dependencies import get_current_user, require_roles, get_tenant_company_id

router = APIRouter(prefix="/dashboard", tags=["Real-Time Operations Dashboard & Analytics"])

@router.get("/realtime", response_model=Dict[str, Any])
def get_realtime_dashboard(
    company_id: str = Depends(get_tenant_company_id),
    current_user: User = Depends(require_roles("admin", "manager")),
    db: Session = Depends(get_db)
):
    now = datetime.now(timezone.utc)
    today_start = datetime(now.year, now.month, now.day, 0, 0, 0, tzinfo=timezone.utc)
    today_date = date.today()

    # 1. Fetch all company employees
    employees = db.query(User).filter(
        User.company_id == company_id,
        User.is_active == True
    ).order_by(User.full_name).all()

    agents_on_call = []
    agents_idle = []
    agents_on_break = []
    agents_offline = []

    for emp in employees:
        status_duration_sec = 0
        if emp.status_updated_at:
            status_duration_sec = max(0, int((now - emp.status_updated_at.replace(tzinfo=timezone.utc)).total_seconds()))

        emp_card = {
            "id": emp.id,
            "full_name": emp.full_name,
            "role": emp.role,
            "status": emp.agent_status,
            "status_duration_sec": status_duration_sec,
            "phone": emp.phone,
            "telephony_agent_id": emp.telephony_agent_id
        }

        if emp.agent_status == "on_call":
            # Find active call
            active_call = db.query(CallLog).filter(
                CallLog.company_id == company_id,
                CallLog.telecaller_id == emp.id,
                CallLog.ended_at.is_(None)
            ).order_by(CallLog.started_at.desc()).first()

            if active_call:
                emp_card["active_call"] = {
                    "call_id": active_call.id,
                    "lead_name": f"{active_call.lead.first_name} {active_call.lead.last_name or ''}".strip() if active_call.lead else "Customer",
                    "callee_number": active_call.callee_number,
                    "duration_sec": max(0, int((now - active_call.started_at.replace(tzinfo=timezone.utc)).total_seconds()))
                }
            agents_on_call.append(emp_card)

        elif emp.agent_status in ("idle", "wrap_up"):
            agents_idle.append(emp_card)

        elif emp.agent_status == "break":
            # Find active break log
            active_break = db.query(BreakLog).join(TelecallerShift).filter(
                TelecallerShift.company_id == company_id,
                TelecallerShift.user_id == emp.id,
                BreakLog.ended_at.is_(None)
            ).order_by(BreakLog.started_at.desc()).first()

            emp_card["break_reason"] = active_break.break_reason if active_break else "Break"
            agents_on_break.append(emp_card)

        else:
            agents_offline.append(emp_card)

    # 2. Company-wide today's call statistics
    calls_today = db.query(CallLog).filter(
        CallLog.company_id == company_id,
        CallLog.started_at >= today_start
    ).all()

    total_calls = len(calls_today)
    connected_calls = sum(1 for c in calls_today if c.status in ("connected", "completed"))
    missed_calls = sum(1 for c in calls_today if c.status in ("missed", "no_answer", "busy", "failed"))
    total_talk_time_sec = sum(c.talk_time_seconds or 0 for c in calls_today)

    avg_call_duration_sec = 0
    if connected_calls > 0:
        avg_call_duration_sec = int(total_talk_time_sec / connected_calls)

    # Leads handled today (unique leads called)
    unique_leads_handled = len(set(c.lead_id for c in calls_today))

    # Converted count today
    converted_stage = db.query(LeadStage).filter(
        LeadStage.company_id == company_id,
        LeadStage.name.ilike("%Converted%")
    ).first()

    conversions_today = 0
    if converted_stage:
        conversions_today = db.query(Lead).filter(
            Lead.company_id == company_id,
            Lead.stage_id == converted_stage.id,
            Lead.updated_at >= today_start
        ).count()

    conversion_rate = 0.0
    if unique_leads_handled > 0:
        conversion_rate = round((conversions_today / unique_leads_handled) * 100, 1)

    return {
        "timestamp": now,
        "summary": {
            "total_calls_today": total_calls,
            "connected_calls": connected_calls,
            "missed_calls": missed_calls,
            "total_talk_time_sec": total_talk_time_sec,
            "average_call_duration_sec": avg_call_duration_sec,
            "leads_handled_today": unique_leads_handled,
            "conversions_today": conversions_today,
            "conversion_rate_percentage": conversion_rate
        },
        "agent_counts": {
            "total": len(employees),
            "on_call": len(agents_on_call),
            "idle": len(agents_idle),
            "on_break": len(agents_on_break),
            "offline": len(agents_offline)
        },
        "agents": {
            "on_call": agents_on_call,
            "idle": agents_idle,
            "on_break": agents_on_break,
            "offline": agents_offline
        }
    }

@router.get("/performance", response_model=List[Dict[str, Any]])
def get_agents_performance_metrics(
    company_id: str = Depends(get_tenant_company_id),
    current_user: User = Depends(require_roles("admin", "manager")),
    db: Session = Depends(get_db)
):
    now = datetime.now(timezone.utc)
    today_start = datetime(now.year, now.month, now.day, 0, 0, 0, tzinfo=timezone.utc)

    telecallers = db.query(User).filter(
        User.company_id == company_id,
        User.role.in_(["telecaller", "manager"]),
        User.is_active == True
    ).order_by(User.full_name).all()

    results = []
    for tc in telecallers:
        # Calls made today
        calls = db.query(CallLog).filter(
            CallLog.company_id == company_id,
            CallLog.telecaller_id == tc.id,
            CallLog.started_at >= today_start
        ).all()

        total_calls = len(calls)
        talk_time_sec = sum(c.talk_time_seconds or 0 for c in calls)
        connected_calls = sum(1 for c in calls if c.status in ("connected", "completed"))

        avg_talk_time = 0
        if connected_calls > 0:
            avg_talk_time = int(talk_time_sec / connected_calls)

        # Assigned leads count
        assigned_leads_count = db.query(Lead).filter(
            Lead.company_id == company_id,
            Lead.assigned_to == tc.id,
            Lead.is_deleted == False
        ).count()

        # Follow-ups completed vs scheduled
        completed_fups = db.query(FollowUp).filter(
            FollowUp.company_id == company_id,
            FollowUp.assigned_to == tc.id,
            FollowUp.status == "completed"
        ).count()

        total_fups = db.query(FollowUp).filter(
            FollowUp.company_id == company_id,
            FollowUp.assigned_to == tc.id
        ).count()

        fup_rate = 0.0
        if total_fups > 0:
            fup_rate = round((completed_fups / total_fups) * 100, 1)

        # Average gap between calls (sec)
        gaps = []
        sorted_calls = sorted(calls, key=lambda x: x.started_at)
        for i in range(1, len(sorted_calls)):
            if sorted_calls[i-1].ended_at:
                gap = (sorted_calls[i].started_at - sorted_calls[i-1].ended_at).total_seconds()
                if 0 <= gap <= 3600:
                    gaps.append(gap)
        avg_gap_sec = int(sum(gaps) / len(gaps)) if gaps else 0

        results.append({
            "agent_id": tc.id,
            "agent_name": tc.full_name,
            "agent_status": tc.agent_status,
            "today_calls_count": total_calls,
            "connected_calls_count": connected_calls,
            "today_talk_time_sec": talk_time_sec,
            "avg_talk_time_sec": avg_talk_time,
            "assigned_leads_count": assigned_leads_count,
            "followup_completion_rate": fup_rate,
            "average_gap_between_calls_sec": avg_gap_sec
        })

    return results

@router.get("/weekly-analytics")
def get_weekly_analytics(
    company_id: str = Depends(get_tenant_company_id),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Returns 7-day call volume trends (connected vs missed) and stage distribution for charts."""
    now = datetime.now(timezone.utc)
    days_labels = []
    connected_series = []
    missed_series = []

    for i in range(6, -1, -1):
        target_date = (now - timedelta(days=i)).date()
        day_str = target_date.strftime("%a") # Mon, Tue, etc.
        days_labels.append(day_str)

        start_dt = datetime(target_date.year, target_date.month, target_date.day, 0, 0, 0, tzinfo=timezone.utc)
        end_dt = start_dt + timedelta(days=1)

        day_calls = db.query(CallLog).filter(
            CallLog.company_id == company_id,
            CallLog.started_at >= start_dt,
            CallLog.started_at < end_dt
        ).all()

        conn = sum(1 for c in day_calls if c.status in ("connected", "completed"))
        miss = sum(1 for c in day_calls if c.status in ("missed", "no_answer", "busy", "failed"))

        connected_series.append(conn)
        missed_series.append(miss)

    # Stage distribution
    stages = db.query(LeadStage).filter(LeadStage.company_id == company_id).order_by(LeadStage.order_index).all()
    total_leads = db.query(Lead).filter(Lead.company_id == company_id, Lead.is_deleted == False).count()

    stage_dist = []
    for s in stages:
        ct = db.query(Lead).filter(Lead.company_id == company_id, Lead.stage_id == s.id, Lead.is_deleted == False).count()
        pct = round((ct / total_leads * 100), 1) if total_leads > 0 else 0.0
        stage_dist.append({
            "id": s.id,
            "name": s.name,
            "color": s.color_hex or "#3B82F6",
            "count": ct,
            "percentage": pct
        })

    return {
        "weekly_chart": {
            "labels": days_labels,
            "connected": connected_series,
            "missed": missed_series
        },
        "stage_distribution": stage_dist,
        "total_leads": total_leads
    }
