import os
import re
import uuid
from fastapi import APIRouter, Depends, HTTPException, status, Query, UploadFile, File
from sqlalchemy.orm import Session
from typing import List, Optional, Dict, Any
from datetime import datetime, timezone

from backend.app.config import settings
from backend.app.database import get_db
from backend.app.models.user import User
from backend.app.models.call import CallLog, CallDisposition
from backend.app.models.lead import Lead
from backend.app.schemas.call import (
    CallDispositionResponse, CallDispositionCreate, CallDispositionUpdate,
    InitiateCallRequest, EndCallRequest, SubmitDispositionRequest,
    CallLogResponse, AgentCallGateStatus
)
from backend.app.services.call_service import (
    initiate_outbound_call, complete_call_session, submit_call_disposition
)
from backend.app.security.dependencies import get_current_user, require_roles, get_tenant_company_id

router = APIRouter(prefix="/calls", tags=["Calling & Dispositions"])

@router.get("/dispositions", response_model=List[CallDispositionResponse])
@router.get("/dispositions/catalog", response_model=List[CallDispositionResponse])
def list_dispositions(
    company_id: str = Depends(get_tenant_company_id),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    disps = db.query(CallDisposition).filter(
        CallDisposition.company_id == company_id,
        CallDisposition.is_active == True
    ).all()
    order_map = {
        "CALL_DISCONNECT": 1,
        "BUSY": 2,
        "RINGING": 3,
        "CALL_BACK": 4,
        "CALLBACK": 4,
        "NOT_INTERESTED": 5,
        "OTHER": 999
    }
    return sorted(disps, key=lambda d: order_map.get(d.code, 50))

@router.post("/dispositions", response_model=CallDispositionResponse)
def create_disposition(
    disp_in: CallDispositionCreate,
    company_id: str = Depends(get_tenant_company_id),
    admin: User = Depends(require_roles("admin")),
    db: Session = Depends(get_db)
):
    label = (disp_in.label or "").strip()
    if not label:
        raise HTTPException(status_code=400, detail="Disposition label is required.")

    raw_code = (disp_in.code or "").strip().upper()
    if not raw_code:
        raw_code = re.sub(r"[^A-Z0-9]+", "_", label.upper()).strip("_")[:40] or f"CUSTOM_{uuid.uuid4().hex[:6].upper()}"

    existing = db.query(CallDisposition).filter(
        CallDisposition.company_id == company_id,
        CallDisposition.code == raw_code
    ).first()
    if existing:
        if not existing.is_active:
            existing.label = label
            existing.requires_followup = disp_in.requires_followup
            existing.is_active = True
            db.commit()
            db.refresh(existing)
            return existing
        # If active with same code, append short suffix so admin can create flexibly
        if existing.label.strip().lower() == label.lower():
            raise HTTPException(status_code=400, detail="A disposition with this name already exists.")
        raw_code = f"{raw_code[:32]}_{uuid.uuid4().hex[:4].upper()}"

    disp = CallDisposition(
        company_id=company_id,
        code=raw_code,
        label=label,
        requires_followup=disp_in.requires_followup,
        is_active=True
    )
    db.add(disp)
    db.commit()
    db.refresh(disp)
    return disp

@router.put("/dispositions/{disposition_id}", response_model=CallDispositionResponse)
def update_disposition(
    disposition_id: str,
    disp_in: CallDispositionUpdate,
    company_id: str = Depends(get_tenant_company_id),
    admin: User = Depends(require_roles("admin")),
    db: Session = Depends(get_db)
):
    disp = db.query(CallDisposition).filter(
        CallDisposition.id == disposition_id,
        CallDisposition.company_id == company_id
    ).first()
    if not disp:
        raise HTTPException(status_code=404, detail="Disposition option not found.")

    if disp_in.label is not None:
        new_label = disp_in.label.strip()
        if not new_label:
            raise HTTPException(status_code=400, detail="Disposition label cannot be empty.")
        disp.label = new_label
    if disp_in.requires_followup is not None:
        disp.requires_followup = disp_in.requires_followup
    if disp_in.is_active is not None:
        disp.is_active = disp_in.is_active

    db.commit()
    db.refresh(disp)
    return disp

@router.delete("/dispositions/{disposition_id}")
def delete_disposition(
    disposition_id: str,
    company_id: str = Depends(get_tenant_company_id),
    admin: User = Depends(require_roles("admin")),
    db: Session = Depends(get_db)
):
    disp = db.query(CallDisposition).filter(
        CallDisposition.id == disposition_id,
        CallDisposition.company_id == company_id
    ).first()
    if not disp:
        raise HTTPException(status_code=404, detail="Disposition option not found.")

    disp.is_active = False
    db.commit()
    return {"status": "deleted", "id": disposition_id}

@router.get("/gate-status", response_model=AgentCallGateStatus)
def check_gate_status(
    company_id: str = Depends(get_tenant_company_id),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Checks if agent has an active undisposed call. Auto-resolves so agent is never hard-blocked.
    """
    undisposed = db.query(CallLog).filter(
        CallLog.company_id == company_id,
        CallLog.telecaller_id == current_user.id,
        CallLog.disposition_id.is_(None)
    ).order_by(CallLog.started_at.desc()).first()

    if undisposed:
        default_disp = db.query(CallDisposition).filter(
            CallDisposition.company_id == company_id,
            CallDisposition.is_active == True
        ).first()
        if default_disp:
            undisposed.disposition_id = default_disp.id
            undisposed.notes = default_disp.label
            undisposed.disposition_submitted_at = datetime.now(timezone.utc)
            db.commit()

    return AgentCallGateStatus(is_blocked=False)

@router.post("/initiate", response_model=Dict[str, Any])
def initiate_call(
    call_req: InitiateCallRequest,
    company_id: str = Depends(get_tenant_company_id),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    call_log = initiate_outbound_call(
        db=db,
        company_id=company_id,
        lead_id=call_req.lead_id,
        phone=call_req.phone,
        agent_user=current_user,
        dial_method=call_req.dial_method or "cloud"
    )
    return {
        "status": "call_initiated",
        "call_log_id": call_log.id,
        "call_sid": call_log.provider_call_sid or call_log.id,
        "callee_number": call_log.callee_number,
        "caller_number": call_log.caller_number,
        "started_at": call_log.started_at,
        "provider_sid": call_log.provider_call_sid
    }

@router.post("/initiate-direct", response_model=Dict[str, Any])
def initiate_direct_call(
    dial_req: Dict[str, Any],
    company_id: str = Depends(get_tenant_company_id),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    phone = str(dial_req.get("phone", "")).strip()
    if not phone or len(phone) < 7:
        raise HTTPException(status_code=400, detail="Please enter a valid phone number (at least 7 digits).")
    dial_method = dial_req.get("dial_method", "cloud")
    call_log = initiate_outbound_call(
        db=db,
        company_id=company_id,
        lead_id=None,
        phone=phone,
        agent_user=current_user,
        dial_method=dial_method
    )
    return {
        "status": "call_initiated",
        "call_log_id": call_log.id,
        "call_sid": call_log.provider_call_sid or call_log.id,
        "callee_number": call_log.callee_number,
        "caller_number": call_log.caller_number,
        "started_at": call_log.started_at,
        "provider_sid": call_log.provider_call_sid
    }

@router.post("/end", response_model=Dict[str, Any])
def end_call(
    req: EndCallRequest,
    company_id: str = Depends(get_tenant_company_id),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    log_id = req.call_log_id or req.call_id
    if not log_id:
        raise HTTPException(status_code=400, detail="Missing call_log_id.")
    call_log = complete_call_session(
        db=db,
        company_id=company_id,
        call_log_id=log_id,
        duration_seconds=req.duration_seconds,
        talk_time_seconds=req.talk_time_seconds,
        call_status=req.status,
        recording_url=req.recording_url
    )
    return {
        "status": "call_ended",
        "call_log_id": call_log.id,
        "duration_seconds": call_log.duration_seconds,
        "recording_url": call_log.recording_url,
        "requires_disposition": True
    }

@router.post("/disposition")
def submit_disposition(
    req: SubmitDispositionRequest,
    company_id: str = Depends(get_tenant_company_id),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    log_id = req.call_log_id or req.call_id
    if not log_id:
        raise HTTPException(status_code=400, detail="Missing call_log_id.")
    call_log = submit_call_disposition(
        db=db,
        company_id=company_id,
        call_log_id=log_id,
        disposition_id=req.disposition_id,
        notes=req.notes or "",
        current_user_id=current_user.id,
        next_followup_at=req.next_followup_at,
        followup_notes=req.followup_notes,
        followup_priority=req.followup_priority or "normal",
        update_lead_stage_id=req.update_lead_stage_id
    )
    return {
        "status": "success",
        "message": "Disposition and notes submitted successfully. Next call unblocked.",
        "call_log_id": call_log.id,
        "disposition_label": call_log.disposition.label if call_log.disposition else None
    }

@router.get("/history", response_model=List[CallLogResponse])
def list_call_logs(
    lead_id: Optional[str] = None,
    limit: int = Query(50, ge=1, le=200),
    company_id: str = Depends(get_tenant_company_id),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    query = db.query(CallLog).filter(CallLog.company_id == company_id)

    if current_user.role == "telecaller":
        query = query.filter(CallLog.telecaller_id == current_user.id)

    if lead_id:
        query = query.filter(CallLog.lead_id == lead_id)

    calls = query.order_by(CallLog.started_at.desc()).limit(limit).all()

    results = []
    for c in calls:
        lead_name = f"{c.lead.first_name} {c.lead.last_name or ''}".strip() if c.lead else "Lead"
        results.append(CallLogResponse(
            id=c.id,
            lead_id=c.lead_id,
            lead_name=lead_name,
            lead_phone=c.callee_number,
            telecaller_id=c.telecaller_id,
            telecaller_name=c.telecaller.full_name if c.telecaller else "Agent",
            direction=c.direction,
            provider_call_sid=c.provider_call_sid,
            caller_number=c.caller_number,
            callee_number=c.callee_number,
            status=c.status,
            started_at=c.started_at,
            answered_at=c.answered_at,
            ended_at=c.ended_at,
            duration_seconds=c.duration_seconds,
            talk_time_seconds=c.talk_time_seconds,
            recording_url=c.recording_url,
            disposition_id=c.disposition_id,
            disposition_label=c.disposition.label if c.disposition else None,
            notes=c.notes,
            disposition_submitted_at=c.disposition_submitted_at
        ))
    return results

@router.post("/{call_log_id}/recording")
async def upload_call_recording(
    call_log_id: str,
    file: UploadFile = File(...),
    company_id: str = Depends(get_tenant_company_id),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    call_log = db.query(CallLog).filter(
        CallLog.id == call_log_id,
        CallLog.company_id == company_id
    ).first()
    if not call_log:
        raise HTTPException(status_code=404, detail="Call log not found.")

    orig_name = file.filename or "recording.webm"
    ext = os.path.splitext(orig_name)[1].lower() or ".webm"
    if ext not in (".mp3", ".m4a", ".wav", ".webm", ".ogg", ".aac", ".mp4"):
        ext = ".webm"

    rec_dir = os.path.join(settings.UPLOAD_DIR, "recordings")
    os.makedirs(rec_dir, exist_ok=True)
    safe_name = f"{call_log.id}_{uuid.uuid4().hex[:8]}{ext}"
    file_path = os.path.join(rec_dir, safe_name)

    content = await file.read()
    with open(file_path, "wb") as f:
        f.write(content)

    call_log.recording_file_path = file_path
    call_log.recording_url = f"/uploads/recordings/{safe_name}"
    call_log.recording_status = "available"
    db.commit()
    db.refresh(call_log)

    return {
        "status": "success",
        "recording_url": call_log.recording_url,
        "filename": safe_name
    }
