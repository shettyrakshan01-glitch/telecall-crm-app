import io
import csv
import re
from typing import List, Dict, Any, Optional
from datetime import datetime, timezone
from sqlalchemy.orm import Session
from sqlalchemy import or_, and_, desc
import openpyxl

from backend.app.models.lead import Lead, LeadStage, LeadAllocation
from backend.app.models.user import User
from backend.app.schemas.lead import (
    LeadCreate, LeadUpdate, LeadImportResult, LeadImportRowError,
    LeadResponse, LeadDetailResponse, LeadAllocationHistoryItem
)
from backend.app.schemas.call import CallLogResponse
from backend.app.schemas.followup import FollowUpResponse

def normalize_phone(phone_str: str) -> str:
    """Cleans phone numbers to standard format (digits only, trims spaces/hyphens)."""
    digits = re.sub(r"[^\d+]", "", str(phone_str).strip())
    # Strip leading zero if 11 digits starting with 0
    if len(digits) == 11 and digits.startswith("0"):
        digits = digits[1:]
    return digits

def check_duplicate_lead(db: Session, company_id: str, phone: str, exclude_lead_id: Optional[str] = None) -> Optional[Lead]:
    phone_clean = normalize_phone(phone)
    query = db.query(Lead).filter(
        Lead.company_id == company_id,
        Lead.is_deleted == False,
        or_(Lead.phone == phone_clean, Lead.phone == phone)
    )
    if exclude_lead_id:
        query = query.filter(Lead.id != exclude_lead_id)
    return query.first()

def create_lead(db: Session, company_id: str, lead_in: LeadCreate, current_user_id: str) -> Lead:
    clean_phone = normalize_phone(lead_in.phone)
    existing = check_duplicate_lead(db, company_id, clean_phone)
    if existing:
        raise ValueError(f"A lead with phone number {clean_phone} already exists in this company (Lead ID: {existing.id}).")

    # If stage_id is not provided, pick or create default 'New' stage
    stage_id = lead_in.stage_id
    if not stage_id:
        default_stage = db.query(LeadStage).filter(
            LeadStage.company_id == company_id,
            LeadStage.name == "New"
        ).first()
        if not default_stage:
            default_stage = LeadStage(company_id=company_id, name="New", color_hex="#3B82F6", order_index=0)
            db.add(default_stage)
            db.flush()
        stage_id = default_stage.id

    lead = Lead(
        company_id=company_id,
        first_name=lead_in.first_name,
        last_name=lead_in.last_name or "",
        phone=clean_phone,
        alternate_phone=normalize_phone(lead_in.alternate_phone) if lead_in.alternate_phone else None,
        email=lead_in.email,
        city=lead_in.city,
        source=lead_in.source or "Manual",
        stage_id=stage_id,
        assigned_to=lead_in.assigned_to,
        assigned_at=datetime.now(timezone.utc) if lead_in.assigned_to else None,
        tags=lead_in.tags or [],
        custom_fields=lead_in.custom_fields or {}
    )
    db.add(lead)
    db.flush()

    # Record initial allocation history if assigned
    if lead_in.assigned_to:
        alloc = LeadAllocation(
            company_id=company_id,
            lead_id=lead.id,
            assigned_by=current_user_id,
            from_user_id=None,
            to_user_id=lead_in.assigned_to,
            transfer_reason="Initial Assignment on Lead Creation"
        )
        db.add(alloc)

    db.commit()
    db.refresh(lead)
    return lead

def parse_and_import_leads(
    db: Session,
    company_id: str,
    file_bytes: bytes,
    filename: str,
    column_mapping: Dict[str, str], # e.g. {"first_name": "Name", "phone": "Mobile", "city": "City"}
    current_user_id: str,
    default_assigned_to: Optional[str] = None
) -> LeadImportResult:
    """
    Imports leads from CSV or Excel file with column mapping, duplicate detection,
    and returns a structured report of successes and failed rows.
    """
    rows_data = []

    if filename.endswith(".csv"):
        text = file_bytes.decode("utf-8-sig", errors="replace")
        csv_reader = csv.DictReader(io.StringIO(text))
        for row in csv_reader:
            rows_data.append(row)
    elif filename.endswith((".xlsx", ".xls")):
        wb = openpyxl.load_workbook(io.BytesIO(file_bytes), data_only=True)
        sheet = wb.active
        headers = [cell.value for cell in sheet[1]]
        for row in sheet.iter_rows(min_row=2, values_only=True):
            if any(row):
                row_dict = {str(headers[i]): (str(row[i]) if row[i] is not None else "") for i in range(len(headers)) if headers[i]}
                rows_data.append(row_dict)
    else:
        raise ValueError("Unsupported file format. Please upload .csv or .xlsx file.")

    default_stage = db.query(LeadStage).filter(
        LeadStage.company_id == company_id,
        LeadStage.name == "New"
    ).first()
    if not default_stage:
        default_stage = LeadStage(company_id=company_id, name="New", color_hex="#3B82F6", order_index=0)
        db.add(default_stage)
        db.flush()

    result = LeadImportResult(
        total_rows=len(rows_data),
        successful_imports=0,
        duplicate_skipped=0,
        failed_rows=0,
        errors=[]
    )

    seen_phones_in_batch = set()

    for idx, row in enumerate(rows_data, start=2): # 1-indexed header is line 1
        name_val = row.get(column_mapping.get("first_name", "first_name"), "").strip()
        phone_val = row.get(column_mapping.get("phone", "phone"), "").strip()
        clean_phone = normalize_phone(phone_val)

        if not clean_phone:
            result.failed_rows += 1
            result.errors.append(LeadImportRowError(
                row_number=idx,
                phone=phone_val,
                reason="Missing or invalid phone number"
            ))
            continue

        if not name_val:
            name_val = f"Lead-{clean_phone[-4:]}"

        if clean_phone in seen_phones_in_batch:
            result.duplicate_skipped += 1
            result.errors.append(LeadImportRowError(
                row_number=idx,
                phone=clean_phone,
                reason="Duplicate phone number inside uploaded file"
            ))
            continue

        existing = check_duplicate_lead(db, company_id, clean_phone)
        if existing:
            result.duplicate_skipped += 1
            result.errors.append(LeadImportRowError(
                row_number=idx,
                phone=clean_phone,
                reason=f"Phone number already exists in CRM (Lead ID: {existing.id})"
            ))
            continue

        seen_phones_in_batch.add(clean_phone)

        # Extract other mapped fields
        city_key = column_mapping.get("city")
        city_val = row.get(city_key, "").strip() if city_key else None
        
        email_key = column_mapping.get("email")
        email_val = row.get(email_key, "").strip() if email_key else None
        
        source_key = column_mapping.get("source")
        source_val = row.get(source_key, "CSV Import").strip() if source_key else "CSV Import"

        new_lead = Lead(
            company_id=company_id,
            first_name=name_val,
            phone=clean_phone,
            email=email_val,
            city=city_val,
            source=source_val or "CSV Import",
            stage_id=default_stage.id,
            assigned_to=default_assigned_to,
            assigned_at=datetime.now(timezone.utc) if default_assigned_to else None,
            tags=["Imported"]
        )
        db.add(new_lead)
        db.flush()

        if default_assigned_to:
            alloc = LeadAllocation(
                company_id=company_id,
                lead_id=new_lead.id,
                assigned_by=current_user_id,
                from_user_id=None,
                to_user_id=default_assigned_to,
                transfer_reason="Batch Import Auto-Assignment"
            )
            db.add(alloc)

        result.successful_imports += 1

    db.commit()
    return result

def get_lead_details(db: Session, company_id: str, lead_id: str) -> Optional[Dict[str, Any]]:
    lead = db.query(Lead).filter(
        Lead.id == lead_id,
        Lead.company_id == company_id,
        Lead.is_deleted == False
    ).first()
    if not lead:
        return None

    # Format allocation history
    history = []
    for alloc in lead.allocation_history:
        history.append({
            "id": alloc.id,
            "assigned_by_name": alloc.assigner.full_name if alloc.assigner else "System",
            "from_user_name": alloc.from_user.full_name if alloc.from_user else "Unassigned",
            "to_user_name": alloc.to_user.full_name if alloc.to_user else "Unassigned",
            "transfer_reason": alloc.transfer_reason or "Assignment",
            "allocated_at": alloc.allocated_at
        })

    # Format call logs
    calls = []
    for call in lead.call_logs:
        calls.append({
            "id": call.id,
            "direction": call.direction,
            "caller_number": call.caller_number,
            "callee_number": call.callee_number,
            "status": call.status,
            "started_at": call.started_at,
            "duration_seconds": call.duration_seconds,
            "talk_time_seconds": call.talk_time_seconds,
            "recording_url": call.recording_url,
            "disposition_label": call.disposition.label if call.disposition else None,
            "notes": call.notes,
            "telecaller_name": call.telecaller.full_name if call.telecaller else "Agent"
        })

    # Format follow-ups
    followups = []
    for f in lead.follow_ups:
        followups.append({
            "id": f.id,
            "scheduled_at": f.scheduled_at,
            "status": f.status,
            "priority": f.priority,
            "notes": f.notes,
            "is_missed_call_callback": f.is_missed_call_callback,
            "assignee_name": f.assignee.full_name if f.assignee else "Agent"
        })

    return {
        "id": lead.id,
        "first_name": lead.first_name,
        "last_name": lead.last_name,
        "phone": lead.phone,
        "alternate_phone": lead.alternate_phone,
        "email": lead.email,
        "city": lead.city,
        "source": lead.source,
        "stage_id": lead.stage_id,
        "stage_name": lead.stage.name if lead.stage else None,
        "stage_color": lead.stage.color_hex if lead.stage else "#3B82F6",
        "assigned_to": lead.assigned_to,
        "assigned_to_name": lead.assignee.full_name if lead.assignee else "Unassigned",
        "total_calls_count": lead.total_calls_count,
        "last_call_at": lead.last_call_at,
        "next_followup_at": lead.next_followup_at,
        "tags": lead.tags or [],
        "custom_fields": lead.custom_fields or {},
        "created_at": lead.created_at,
        "updated_at": lead.updated_at,
        "allocation_history": history,
        "call_logs": calls,
        "follow_ups": followups
    }
