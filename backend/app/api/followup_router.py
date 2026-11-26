from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from typing import List, Optional, Dict, Any

from backend.app.database import get_db
from backend.app.models.user import User
from backend.app.models.followup import FollowUp
from backend.app.schemas.followup import (
    FollowUpCreate, FollowUpUpdate, FollowUpResponse, FollowUpSummary
)
from backend.app.services.followup_service import (
    create_followup, get_followups_by_filter, get_followup_counts, update_followup_status
)
from backend.app.security.dependencies import get_current_user, get_tenant_company_id

router = APIRouter(prefix="/followups", tags=["Follow-ups & Reminders"])

@router.get("", response_model=List[Dict[str, Any]])
def list_followups(
    filter_type: str = Query("today", description="today, tomorrow, overdue, all"),
    status: str = Query("pending", description="pending, completed, all"),
    company_id: str = Depends(get_tenant_company_id),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    assigned_to = None
    if current_user.role == "telecaller":
        assigned_to = current_user.id # Telecaller sees only their own follow-ups

    return get_followups_by_filter(
        db=db,
        company_id=company_id,
        filter_type=filter_type,
        assigned_to=assigned_to,
        status_filter=status
    )

@router.get("/summary", response_model=FollowUpSummary)
def get_summary(
    company_id: str = Depends(get_tenant_company_id),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    assigned_to = None
    if current_user.role == "telecaller":
        assigned_to = current_user.id

    counts = get_followup_counts(db, company_id, assigned_to)
    return FollowUpSummary(
        today_count=counts["today_count"],
        tomorrow_count=counts["tomorrow_count"],
        overdue_count=counts["overdue_count"],
        completed_today_count=counts["completed_today_count"]
    )

@router.post("", response_model=FollowUpResponse)
def add_followup(
    fup_in: FollowUpCreate,
    company_id: str = Depends(get_tenant_company_id),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    assigned_target = fup_in.assigned_to or current_user.id
    if current_user.role == "telecaller":
        assigned_target = current_user.id

    target_lead_id = fup_in.lead_id
    if not target_lead_id and fup_in.call_log_id:
        from backend.app.models.call import CallLog
        c_log = db.query(CallLog).filter(CallLog.id == fup_in.call_log_id, CallLog.company_id == company_id).first()
        if c_log:
            target_lead_id = c_log.lead_id

    if not target_lead_id:
        from backend.app.models.lead import Lead
        first_lead = db.query(Lead).filter(Lead.company_id == company_id, Lead.is_deleted == False).first()
        if not first_lead:
            raise HTTPException(status_code=400, detail="Cannot schedule follow-up without an associated lead.")
        target_lead_id = first_lead.id

    fup = create_followup(
        db=db,
        company_id=company_id,
        lead_id=target_lead_id,
        scheduled_at=fup_in.scheduled_at,
        assigned_to=assigned_target,
        created_by=current_user.id,
        priority=fup_in.priority,
        notes=fup_in.notes,
        call_log_id=fup_in.call_log_id
    )

    return FollowUpResponse(
        id=fup.id,
        lead_id=fup.lead_id,
        lead_name=fup.lead.first_name + (" " + fup.lead.last_name if fup.lead.last_name else ""),
        lead_phone=fup.lead.phone,
        lead_city=fup.lead.city,
        assigned_to=fup.assigned_to,
        assigned_to_name=fup.assignee.full_name if fup.assignee else "Agent",
        scheduled_at=fup.scheduled_at,
        status=fup.status,
        priority=fup.priority,
        is_missed_call_callback=fup.is_missed_call_callback,
        notes=fup.notes,
        completed_at=fup.completed_at,
        created_at=fup.created_at
    )

@router.put("/{followup_id}/complete")
def mark_completed(
    followup_id: str,
    notes: Optional[str] = None,
    company_id: str = Depends(get_tenant_company_id),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    fup = update_followup_status(db, company_id, followup_id, "completed", notes)
    return {"status": "success", "message": "Follow-up marked as completed."}

@router.put("/{followup_id}")
def update_followup(
    followup_id: str,
    update_data: FollowUpUpdate,
    company_id: str = Depends(get_tenant_company_id),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    fup = db.query(FollowUp).filter(FollowUp.id == followup_id, FollowUp.company_id == company_id).first()
    if not fup:
        raise HTTPException(status_code=404, detail="Follow-up not found.")

    if update_data.scheduled_at:
        fup.scheduled_at = update_data.scheduled_at
        if fup.lead:
            fup.lead.next_followup_at = update_data.scheduled_at
    if update_data.status:
        fup.status = update_data.status
    if update_data.priority:
        fup.priority = update_data.priority
    if update_data.notes:
        fup.notes = update_data.notes

    db.commit()
    db.refresh(fup)
    return {"status": "success", "message": "Follow-up updated."}
