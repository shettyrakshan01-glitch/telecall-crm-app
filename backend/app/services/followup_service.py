from datetime import datetime, timezone, timedelta, date
from typing import List, Optional, Dict, Any
from sqlalchemy.orm import Session
from sqlalchemy import and_, or_
from fastapi import HTTPException

from backend.app.models.followup import FollowUp
from backend.app.models.lead import Lead
from backend.app.models.user import User

def create_followup(
    db: Session,
    company_id: str,
    lead_id: str,
    scheduled_at: datetime,
    assigned_to: str,
    created_by: str,
    priority: str = "normal",
    notes: Optional[str] = None,
    call_log_id: Optional[str] = None,
    is_missed_call: bool = False
) -> FollowUp:
    lead = db.query(Lead).filter(Lead.id == lead_id, Lead.company_id == company_id).first()
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found.")

    followup = FollowUp(
        company_id=company_id,
        lead_id=lead_id,
        call_log_id=call_log_id,
        assigned_to=assigned_to,
        created_by=created_by,
        scheduled_at=scheduled_at,
        priority=priority,
        notes=notes,
        is_missed_call_callback=is_missed_call,
        status="pending"
    )
    db.add(followup)

    # Sync next_followup_at on the lead
    lead.next_followup_at = scheduled_at

    db.commit()
    db.refresh(followup)
    return followup

def get_followups_by_filter(
    db: Session,
    company_id: str,
    filter_type: str, # "today", "tomorrow", "overdue", "all"
    assigned_to: Optional[str] = None, # None means all agents (for admin)
    status_filter: str = "pending"
) -> List[Dict[str, Any]]:
    now = datetime.now(timezone.utc)
    today_start = datetime(now.year, now.month, now.day, 0, 0, 0, tzinfo=timezone.utc)
    today_end = today_start + timedelta(days=1)
    tomorrow_end = today_end + timedelta(days=1)

    query = db.query(FollowUp).join(Lead).filter(
        FollowUp.company_id == company_id
    )

    if assigned_to:
        query = query.filter(FollowUp.assigned_to == assigned_to)

    if status_filter != "all":
        query = query.filter(FollowUp.status == status_filter)

    if filter_type == "today":
        query = query.filter(
            FollowUp.scheduled_at >= today_start,
            FollowUp.scheduled_at < today_end
        )
    elif filter_type == "tomorrow":
        query = query.filter(
            FollowUp.scheduled_at >= today_end,
            FollowUp.scheduled_at < tomorrow_end
        )
    elif filter_type == "overdue":
        query = query.filter(
            FollowUp.scheduled_at < now,
            FollowUp.status == "pending"
        )

    results = query.order_by(FollowUp.scheduled_at.asc()).all()

    formatted = []
    for f in results:
        formatted.append({
            "id": f.id,
            "lead_id": f.lead_id,
            "lead_name": f.lead.first_name + (" " + f.lead.last_name if f.lead.last_name else ""),
            "lead_phone": f.lead.phone,
            "lead_city": f.lead.city,
            "lead_stage": f.lead.stage.name if f.lead.stage else None,
            "assigned_to": f.assigned_to,
            "assigned_to_name": f.assignee.full_name if f.assignee else "Agent",
            "scheduled_at": f.scheduled_at,
            "status": f.status,
            "priority": f.priority,
            "is_missed_call_callback": f.is_missed_call_callback,
            "notes": f.notes,
            "created_at": f.created_at
        })
    return formatted

def get_followup_counts(db: Session, company_id: str, assigned_to: Optional[str] = None) -> Dict[str, int]:
    now = datetime.now(timezone.utc)
    today_start = datetime(now.year, now.month, now.day, 0, 0, 0, tzinfo=timezone.utc)
    today_end = today_start + timedelta(days=1)
    tomorrow_end = today_end + timedelta(days=1)

    base = db.query(FollowUp).filter(FollowUp.company_id == company_id)
    if assigned_to:
        base = base.filter(FollowUp.assigned_to == assigned_to)

    today_count = base.filter(
        FollowUp.scheduled_at >= today_start,
        FollowUp.scheduled_at < today_end,
        FollowUp.status == "pending"
    ).count()

    tomorrow_count = base.filter(
        FollowUp.scheduled_at >= today_end,
        FollowUp.scheduled_at < tomorrow_end,
        FollowUp.status == "pending"
    ).count()

    overdue_count = base.filter(
        FollowUp.scheduled_at < now,
        FollowUp.status == "pending"
    ).count()

    completed_today = base.filter(
        FollowUp.completed_at >= today_start,
        FollowUp.status == "completed"
    ).count()

    return {
        "today_count": today_count,
        "tomorrow_count": tomorrow_count,
        "overdue_count": overdue_count,
        "completed_today_count": completed_today
    }

def update_followup_status(db: Session, company_id: str, followup_id: str, new_status: str, notes: Optional[str] = None) -> FollowUp:
    followup = db.query(FollowUp).filter(
        FollowUp.id == followup_id,
        FollowUp.company_id == company_id
    ).first()
    if not followup:
        raise HTTPException(status_code=404, detail="Follow-up not found.")

    followup.status = new_status
    if notes:
        followup.notes = (followup.notes or "") + f"\n[{datetime.now().strftime('%Y-%m-%d %H:%M')}] {notes}"
    if new_status == "completed":
        followup.completed_at = datetime.now(timezone.utc)

    db.commit()
    db.refresh(followup)
    return followup
