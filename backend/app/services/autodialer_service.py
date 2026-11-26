from datetime import datetime, timezone
from typing import Dict, Any, Optional, List
from sqlalchemy.orm import Session
from fastapi import HTTPException, status

from backend.app.models.autodialer import AutoDialerSession
from backend.app.models.lead import Lead
from backend.app.models.user import User
from backend.app.models.call import CallLog
from backend.app.services.lead_service import get_lead_details
from backend.app.services.call_service import initiate_outbound_call

def create_dialer_session(
    db: Session,
    company_id: str,
    user: User,
    name: str,
    mode: str,
    countdown_seconds: int,
    filter_stage_id: Optional[str] = None,
    custom_lead_ids: Optional[List[str]] = None
) -> AutoDialerSession:
    lead_ids = []

    if custom_lead_ids:
        # User explicitly passed a list of leads
        leads = db.query(Lead).filter(
            Lead.id.in_(custom_lead_ids),
            Lead.company_id == company_id,
            Lead.is_deleted == False
        ).all()
        lead_ids = [l.id for l in leads]
    else:
        # Pull assigned leads
        query = db.query(Lead).filter(
            Lead.company_id == company_id,
            Lead.is_deleted == False
        )
        if user.role == "telecaller":
            query = query.filter(Lead.assigned_to == user.id)

        if filter_stage_id:
            query = query.filter(Lead.stage_id == filter_stage_id)

        leads = query.order_by(Lead.total_calls_count.asc(), Lead.created_at.desc()).limit(150).all()
        lead_ids = [l.id for l in leads]

    if not lead_ids:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No leads found for this auto-dialer campaign."
        )

    # Terminate any previously running session for this user
    db.query(AutoDialerSession).filter(
        AutoDialerSession.company_id == company_id,
        AutoDialerSession.user_id == user.id,
        AutoDialerSession.status.in_(["running", "paused"])
    ).update({"status": "stopped"})

    session = AutoDialerSession(
        company_id=company_id,
        user_id=user.id,
        name=name or f"Auto-Dialer ({mode.capitalize()})",
        mode=mode,
        countdown_seconds=countdown_seconds or 10,
        status="running",
        lead_ids=lead_ids,
        current_index=0,
        total_leads=len(lead_ids),
        dialed_count=0,
        connected_count=0,
        skipped_count=0
    )
    db.add(session)
    db.commit()
    db.refresh(session)
    return session

def get_dialer_session_state(db: Session, company_id: str, session_id: str, user_id: str) -> Dict[str, Any]:
    session = db.query(AutoDialerSession).filter(
        AutoDialerSession.id == session_id,
        AutoDialerSession.company_id == company_id,
        AutoDialerSession.user_id == user_id
    ).first()
    if not session:
        raise HTTPException(status_code=404, detail="Auto-dialer session not found.")

    # Check if agent has an undisposed call blocking them
    undisposed = db.query(CallLog).filter(
        CallLog.company_id == company_id,
        CallLog.telecaller_id == user_id,
        CallLog.disposition_id.is_(None)
    ).order_by(CallLog.started_at.desc()).first()

    is_blocked_by_call = undisposed is not None

    current_lead = None
    is_finished = session.current_index >= session.total_leads

    if not is_finished:
        curr_lead_id = session.lead_ids[session.current_index]
        current_lead = get_lead_details(db, company_id, curr_lead_id)

    progress = 0.0
    if session.total_leads > 0:
        progress = round((session.current_index / session.total_leads) * 100, 1)

    return {
        "session_id": session.id,
        "name": session.name,
        "mode": session.mode,
        "status": "completed" if is_finished else session.status,
        "current_index": min(session.current_index + 1, session.total_leads),
        "total_leads": session.total_leads,
        "progress_percentage": progress,
        "countdown_seconds": session.countdown_seconds,
        "dialed_count": session.dialed_count,
        "connected_count": session.connected_count,
        "skipped_count": session.skipped_count,
        "is_blocked_by_call": is_blocked_by_call,
        "blocking_call_id": undisposed.id if undisposed else None,
        "is_finished": is_finished,
        "lead": current_lead
    }

def dial_session_lead(db: Session, company_id: str, session_id: str, user: User) -> Dict[str, Any]:
    session = db.query(AutoDialerSession).filter(
        AutoDialerSession.id == session_id,
        AutoDialerSession.company_id == company_id,
        AutoDialerSession.user_id == user.id
    ).first()
    if not session:
        raise HTTPException(status_code=404, detail="Session not found.")

    if session.current_index >= session.total_leads:
        session.status = "completed"
        db.commit()
        return {"status": "finished", "message": "Campaign leads exhausted."}

    curr_lead_id = session.lead_ids[session.current_index]
    
    # Trigger outbound call (enforces call gate)
    call_log = initiate_outbound_call(db, company_id, curr_lead_id, user)
    
    session.dialed_count += 1
    session.connected_count += 1
    db.commit()

    return {
        "status": "dialing",
        "call_log_id": call_log.id,
        "lead_id": curr_lead_id,
        "callee_number": call_log.callee_number,
        "provider_sid": call_log.provider_call_sid
    }

def advance_session_queue(db: Session, company_id: str, session_id: str, user_id: str, skipped: bool = False) -> Dict[str, Any]:
    session = db.query(AutoDialerSession).filter(
        AutoDialerSession.id == session_id,
        AutoDialerSession.company_id == company_id,
        AutoDialerSession.user_id == user_id
    ).first()
    if not session:
        raise HTTPException(status_code=404, detail="Session not found.")

    if skipped:
        session.skipped_count += 1

    session.current_index += 1
    if session.current_index >= session.total_leads:
        session.status = "completed"

    session.updated_at = datetime.now(timezone.utc)
    db.commit()
    return get_dialer_session_state(db, company_id, session.id, user_id)

def set_session_status(db: Session, company_id: str, session_id: str, user_id: str, new_status: str) -> AutoDialerSession:
    session = db.query(AutoDialerSession).filter(
        AutoDialerSession.id == session_id,
        AutoDialerSession.company_id == company_id,
        AutoDialerSession.user_id == user_id
    ).first()
    if not session:
        raise HTTPException(status_code=404, detail="Session not found.")

    session.status = new_status
    session.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(session)
    return session
