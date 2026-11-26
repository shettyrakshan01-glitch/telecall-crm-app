from datetime import datetime, timezone, timedelta
from typing import Dict, Any, Optional
from sqlalchemy.orm import Session
from fastapi import HTTPException, status

from backend.app.models.call import CallLog, CallDisposition
from backend.app.models.lead import Lead, LeadStage
from backend.app.models.user import User, TelecallerShift
from backend.app.models.company import TelephonyConfig
from backend.app.services.telephony.factory import TelephonyFactory
from backend.app.services.followup_service import create_followup
from backend.app.services.notification_service import notify_missed_call
from backend.app.security.dependencies import verify_call_gate_clear

def initiate_outbound_call(
    db: Session,
    company_id: str,
    lead_id: Optional[str],
    agent_user: User,
    dial_method: str = "cloud",
    phone: Optional[str] = None
) -> CallLog:
    # 1. Enforce Mandatory Call Gate: Next call is BLOCKED until previous call disposition is submitted
    verify_call_gate_clear(agent_user.id, company_id, db)

    # 2. Fetch Lead or match/create from phone
    lead = None
    if lead_id:
        lead = db.query(Lead).filter(
            Lead.id == lead_id,
            Lead.company_id == company_id,
            Lead.is_deleted == False
        ).first()

    clean_phone = phone.strip() if phone else None
    if not lead and clean_phone:
        # Check if lead exists with this phone number
        lead = db.query(Lead).filter(
            Lead.company_id == company_id,
            Lead.phone == clean_phone,
            Lead.is_deleted == False
        ).first()

        if not lead:
            # Auto-create contact record for direct dial
            first_stage = db.query(LeadStage).filter(
                LeadStage.company_id == company_id
            ).order_by(LeadStage.order_index).first()

            lead = Lead(
                company_id=company_id,
                first_name="Contact",
                last_name=clean_phone[-4:] if len(clean_phone) >= 4 else clean_phone,
                phone=clean_phone,
                source="Manual Keypad",
                stage_id=first_stage.id if first_stage else None,
                assigned_to=agent_user.id
            )
            db.add(lead)
            db.commit()
            db.refresh(lead)

    if not lead:
        raise HTTPException(status_code=404, detail="Lead or valid phone number not found.")

    now = datetime.now(timezone.utc)
    call_sid = None

    # 3. Handle Dial Method: SIM vs Cloud Telephony
    if dial_method == "sim":
        call_sid = f"sim_{int(now.timestamp())}"
        consent_announced = False
    else:
        # Fetch Company Telephony Configuration
        telephony_config = db.query(TelephonyConfig).filter(
            TelephonyConfig.company_id == company_id
        ).first()

        provider_name = telephony_config.provider if telephony_config else "mock"
        virtual_number = telephony_config.virtual_number if telephony_config else "1800-DEMO-CALL"
        config_dict = {
            "api_key": telephony_config.api_key if telephony_config else "",
            "api_token": telephony_config.api_token if telephony_config else "",
            "account_sid": telephony_config.account_sid if telephony_config else ""
        }

        provider = TelephonyFactory.get_provider(provider_name)
        call_result = provider.initiate_call(
            agent_number=agent_user.phone,
            customer_number=lead.phone,
            virtual_number=virtual_number,
            config=config_dict
        )
        call_sid = call_result.call_sid
        consent_announced = telephony_config.recording_consent_enabled if telephony_config else True

    # 4. Create Call Log in Database
    call_log = CallLog(
        company_id=company_id,
        lead_id=lead.id,
        telecaller_id=agent_user.id,
        direction="outbound",
        provider_call_sid=call_sid,
        caller_number=agent_user.phone or "SIM",
        callee_number=lead.phone,
        status="connected", # initiated / connected
        started_at=now,
        consent_announced=consent_announced
    )
    db.add(call_log)

    # Update Lead Stats
    lead.total_calls_count += 1
    lead.last_call_at = now

    # Update Agent Status
    agent_user.agent_status = "on_call"
    agent_user.status_updated_at = now

    db.commit()
    db.refresh(call_log)
    return call_log

def complete_call_session(
    db: Session,
    company_id: str,
    call_log_id: str,
    duration_seconds: int,
    talk_time_seconds: int,
    call_status: str,
    recording_url: Optional[str] = None
) -> CallLog:
    call_log = db.query(CallLog).filter(
        CallLog.id == call_log_id,
        CallLog.company_id == company_id
    ).first()
    if not call_log:
        raise HTTPException(status_code=404, detail="Call log not found.")

    now = datetime.now(timezone.utc)
    call_log.ended_at = now
    call_log.duration_seconds = max(0, duration_seconds)
    call_log.talk_time_seconds = max(0, talk_time_seconds)
    call_log.status = call_status
    if recording_url:
        call_log.recording_url = recording_url
    elif not call_log.recording_url:
        provider = TelephonyFactory.get_provider("mock")
        call_log.recording_url = provider.fetch_recording_url(call_log.provider_call_sid, {})

    # Agent transitions to wrap_up status until disposition is submitted
    agent = db.query(User).filter(User.id == call_log.telecaller_id).first()
    if agent:
        agent.agent_status = "wrap_up"
        agent.status_updated_at = now

    # If call was missed or unanswered, auto-schedule a callback task and notify agent
    if call_status in ("missed", "no_answer", "busy", "failed"):
        callback_time = now + timedelta(hours=2) # Default retry in 2 hours
        create_followup(
            db=db,
            company_id=company_id,
            lead_id=call_log.lead_id,
            call_log_id=call_log.id,
            assigned_to=call_log.telecaller_id,
            created_by=call_log.telecaller_id,
            scheduled_at=callback_time,
            priority="high",
            notes=f"Auto-generated callback: Call status was '{call_status.upper()}'. Please re-attempt contact.",
            is_missed_call=True
        )
        lead = db.query(Lead).filter(Lead.id == call_log.lead_id).first()
        lead_name = f"{lead.first_name} {lead.last_name or ''}".strip() if lead else "Lead"
        lead_phone = lead.phone if lead else call_log.callee_number
        notify_missed_call(db, company_id, call_log.telecaller_id, lead_name, lead_phone, call_log.lead_id)

    db.commit()
    db.refresh(call_log)
    return call_log

def submit_call_disposition(
    db: Session,
    company_id: str,
    call_log_id: str,
    disposition_id: str,
    notes: str,
    current_user_id: str,
    next_followup_at: Optional[datetime] = None,
    followup_notes: Optional[str] = None,
    followup_priority: str = "normal",
    update_lead_stage_id: Optional[str] = None
) -> CallLog:
    call_log = db.query(CallLog).filter(
        CallLog.id == call_log_id,
        CallLog.company_id == company_id
    ).first()
    if not call_log:
        raise HTTPException(status_code=404, detail="Call log not found.")

    disposition = db.query(CallDisposition).filter(
        CallDisposition.id == disposition_id,
        CallDisposition.company_id == company_id
    ).first()
    if not disposition:
        raise HTTPException(status_code=404, detail="Invalid disposition selected.")

    now = datetime.now(timezone.utc)
    call_log.disposition_id = disposition.id
    call_log.notes = (notes or disposition.label or "").strip()
    call_log.disposition_submitted_at = now

    # Reset agent status back to idle
    agent = db.query(User).filter(User.id == current_user_id).first()
    if agent and agent.agent_status in ("on_call", "wrap_up"):
        agent.agent_status = "idle"
        agent.status_updated_at = now

    # Update Shift statistics
    today = now.date()
    shift = db.query(TelecallerShift).filter(
        TelecallerShift.company_id == company_id,
        TelecallerShift.user_id == current_user_id,
        TelecallerShift.shift_date == today
    ).first()
    if shift:
        shift.total_talk_time_sec = (shift.total_talk_time_sec or 0) + (call_log.talk_time_seconds or 0)
        shift.total_calls_handled = (shift.total_calls_handled or 0) + 1

    # Update Lead Stage if specified or auto-matched
    lead = db.query(Lead).filter(Lead.id == call_log.lead_id).first()
    if lead:
        if update_lead_stage_id:
            lead.stage_id = update_lead_stage_id
        else:
            # Auto-match disposition label to stage name if exists
            matched_stage = db.query(LeadStage).filter(
                LeadStage.company_id == company_id,
                LeadStage.name.ilike(disposition.label)
            ).first()
            if not matched_stage and disposition.code in ("CALL_BACK", "CALLBACK"):
                matched_stage = db.query(LeadStage).filter(
                    LeadStage.company_id == company_id,
                    LeadStage.name.ilike("%callback%")
                ).first()
            if matched_stage:
                lead.stage_id = matched_stage.id

    # Create follow-up if requested or required by disposition
    if next_followup_at:
        create_followup(
            db=db,
            company_id=company_id,
            lead_id=call_log.lead_id,
            call_log_id=call_log.id,
            assigned_to=current_user_id,
            created_by=current_user_id,
            scheduled_at=next_followup_at,
            priority=followup_priority or "normal",
            notes=(followup_notes or notes or f"Callback: {disposition.label}").strip()
        )

    db.commit()
    db.refresh(call_log)
    return call_log
