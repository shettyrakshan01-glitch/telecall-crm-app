from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import Dict, Any

from backend.app.database import get_db
from backend.app.models.user import User
from backend.app.schemas.autodialer import StartDialerRequest, AutoDialerSessionResponse, DialerNextLeadResponse
from backend.app.services.autodialer_service import (
    create_dialer_session, get_dialer_session_state, dial_session_lead,
    advance_session_queue, set_session_status
)
from backend.app.security.dependencies import get_current_user, get_tenant_company_id

router = APIRouter(prefix="/autodialer", tags=["Auto-Dialer Engine"])

@router.post("/start", response_model=Dict[str, Any])
def start_autodialer_session(
    req: StartDialerRequest,
    company_id: str = Depends(get_tenant_company_id),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    session = create_dialer_session(
        db=db,
        company_id=company_id,
        user=current_user,
        name=req.name,
        mode=req.mode,
        countdown_seconds=req.countdown_seconds,
        filter_stage_id=req.filter_stage_id,
        custom_lead_ids=req.custom_lead_ids
    )
    return get_dialer_session_state(db, company_id, session.id, current_user.id)

@router.get("/session/{session_id}", response_model=Dict[str, Any])
def get_session_status(
    session_id: str,
    company_id: str = Depends(get_tenant_company_id),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    return get_dialer_session_state(db, company_id, session_id, current_user.id)

@router.post("/session/{session_id}/dial")
def dial_current(
    session_id: str,
    company_id: str = Depends(get_tenant_company_id),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    return dial_session_lead(db, company_id, session_id, current_user)

@router.post("/session/{session_id}/skip")
def skip_lead(
    session_id: str,
    company_id: str = Depends(get_tenant_company_id),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    return advance_session_queue(db, company_id, session_id, current_user.id, skipped=True)

@router.post("/session/{session_id}/advance")
def advance_to_next(
    session_id: str,
    company_id: str = Depends(get_tenant_company_id),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    return advance_session_queue(db, company_id, session_id, current_user.id, skipped=False)

@router.post("/session/{session_id}/pause")
def pause_dialer(
    session_id: str,
    company_id: str = Depends(get_tenant_company_id),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    session = set_session_status(db, company_id, session_id, current_user.id, "paused")
    return {"status": "paused", "session_id": session.id}

@router.post("/session/{session_id}/resume")
def resume_dialer(
    session_id: str,
    company_id: str = Depends(get_tenant_company_id),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    session = set_session_status(db, company_id, session_id, current_user.id, "running")
    return {"status": "running", "session_id": session.id}

@router.post("/session/{session_id}/stop")
def stop_dialer(
    session_id: str,
    company_id: str = Depends(get_tenant_company_id),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    session = set_session_status(db, company_id, session_id, current_user.id, "stopped")
    return {"status": "stopped", "session_id": session.id}
