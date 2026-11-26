from fastapi import APIRouter, Depends, HTTPException, status, Request, Response
from sqlalchemy.orm import Session
from typing import Dict, Any, Optional
from datetime import datetime, timezone

from backend.app.database import get_db
from backend.app.models.user import User
from backend.app.models.company import TelephonyConfig, Company
from backend.app.models.call import CallLog
from backend.app.schemas.company import TelephonyConfigResponse, TelephonyConfigUpdate
from backend.app.services.call_service import complete_call_session
from backend.app.security.dependencies import require_roles, get_tenant_company_id

router = APIRouter(prefix="/telephony", tags=["Telephony & Webhooks"])

@router.get("/config", response_model=TelephonyConfigResponse)
def get_company_telephony_config(
    company_id: str = Depends(get_tenant_company_id),
    current_user: User = Depends(require_roles("admin")),
    db: Session = Depends(get_db)
):
    config = db.query(TelephonyConfig).filter(TelephonyConfig.company_id == company_id).first()
    if not config:
        config = TelephonyConfig(
            company_id=company_id,
            provider="mock",
            virtual_number="1800-DEMO-CALL",
            recording_consent_enabled=True,
            retention_days=30
        )
        db.add(config)
        db.commit()
        db.refresh(config)

    return TelephonyConfigResponse(
        id=config.id,
        provider=config.provider,
        virtual_number=config.virtual_number,
        recording_consent_enabled=config.recording_consent_enabled,
        consent_announcement_text=config.consent_announcement_text,
        retention_days=config.retention_days,
        is_active=config.is_active,
        allow_manual_dialing=getattr(config, "allow_manual_dialing", True),
        working_hours_start=getattr(config, "working_hours_start", "09:00"),
        working_hours_end=getattr(config, "working_hours_end", "19:00"),
        allow_agent_bulk_upload=getattr(config, "allow_agent_bulk_upload", False)
    )

@router.put("/config", response_model=TelephonyConfigResponse)
def update_company_telephony_config(
    config_in: TelephonyConfigUpdate,
    company_id: str = Depends(get_tenant_company_id),
    current_user: User = Depends(require_roles("admin")),
    db: Session = Depends(get_db)
):
    config = db.query(TelephonyConfig).filter(TelephonyConfig.company_id == company_id).first()
    if not config:
        config = TelephonyConfig(company_id=company_id)
        db.add(config)

    config.provider = config_in.provider.lower().strip()
    config.api_key = config_in.api_key.strip()
    config.api_token = config_in.api_token.strip()
    if config_in.account_sid is not None:
        config.account_sid = config_in.account_sid.strip()
    config.virtual_number = config_in.virtual_number.strip()
    if config_in.webhook_secret is not None:
        config.webhook_secret = config_in.webhook_secret.strip()
    config.recording_consent_enabled = config_in.recording_consent_enabled
    config.consent_announcement_text = config_in.consent_announcement_text
    config.retention_days = config_in.retention_days
    config.is_active = config_in.is_active
    if config_in.allow_manual_dialing is not None:
        config.allow_manual_dialing = config_in.allow_manual_dialing
    if config_in.working_hours_start is not None:
        config.working_hours_start = config_in.working_hours_start
    if config_in.working_hours_end is not None:
        config.working_hours_end = config_in.working_hours_end
    if config_in.allow_agent_bulk_upload is not None:
        config.allow_agent_bulk_upload = config_in.allow_agent_bulk_upload

    db.commit()
    db.refresh(config)

    return TelephonyConfigResponse(
        id=config.id,
        provider=config.provider,
        virtual_number=config.virtual_number,
        recording_consent_enabled=config.recording_consent_enabled,
        consent_announcement_text=config.consent_announcement_text,
        retention_days=config.retention_days,
        is_active=config.is_active,
        allow_manual_dialing=config.allow_manual_dialing,
        working_hours_start=config.working_hours_start,
        working_hours_end=config.working_hours_end,
        allow_agent_bulk_upload=config.allow_agent_bulk_upload
    )

@router.post("/webhook/{provider}")
async def telephony_provider_webhook(
    provider: str,
    request: Request,
    db: Session = Depends(get_db)
):
    """
    Universal webhook receiver for telephony events (Exotel, Twilio, Ozonetel, Knowlarity, MyOperator).
    Extracts Call SID, status, duration, and recording audio URL.
    """
    form_data = {}
    try:
        form_data = await request.form()
    except Exception:
        pass

    json_data = {}
    try:
        json_data = await request.json()
    except Exception:
        pass

    # Merge payloads (form or JSON)
    payload = {**form_data, **json_data}

    # Normalize fields across providers
    call_sid = (
        payload.get("CallSid") or 
        payload.get("call_sid") or 
        payload.get("sid") or 
        payload.get("CallId") or 
        payload.get("call_id")
    )
    status_raw = (
        payload.get("Status") or 
        payload.get("status") or 
        payload.get("CallStatus") or 
        payload.get("call_status") or 
        "completed"
    ).lower()

    duration_raw = (
        payload.get("Duration") or 
        payload.get("duration") or 
        payload.get("DialCallDuration") or 
        payload.get("talk_time") or 
        0
    )
    try:
        duration_sec = int(duration_raw)
    except (ValueError, TypeError):
        duration_sec = 0

    recording_url = (
        payload.get("RecordingUrl") or 
        payload.get("recording_url") or 
        payload.get("record_file") or 
        payload.get("Recording")
    )

    if not call_sid:
        return {"status": "ignored", "reason": "No Call SID found in webhook payload."}

    # Find matching call log
    call_log = db.query(CallLog).filter(CallLog.provider_call_sid == call_sid).first()
    if not call_log:
        return {"status": "not_found", "call_sid": call_sid}

    # Map provider status to standard enum
    standard_status = "completed"
    if status_raw in ("completed", "answered", "success"):
        standard_status = "completed"
    elif status_raw in ("busy", "no-answer", "no_answer", "timeout"):
        standard_status = "no_answer"
    elif status_raw in ("missed", "canceled", "failed"):
        standard_status = "missed"

    complete_call_session(
        db=db,
        company_id=call_log.company_id,
        call_log_id=call_log.id,
        duration_seconds=duration_sec,
        talk_time_seconds=max(0, duration_sec - 3),
        call_status=standard_status,
        recording_url=recording_url
    )

    return {
        "status": "processed",
        "call_log_id": call_log.id,
        "call_sid": call_sid,
        "recorded": recording_url is not None
    }
