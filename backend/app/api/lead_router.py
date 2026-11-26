import json
from fastapi import APIRouter, Depends, HTTPException, status, Query, UploadFile, File, Form
from sqlalchemy.orm import Session
from sqlalchemy import or_, and_, desc
from typing import List, Optional, Dict, Any
from datetime import datetime

from backend.app.database import get_db
from backend.app.models.lead import Lead, LeadStage, LeadAllocation
from backend.app.models.user import User
from backend.app.schemas.lead import (
    LeadCreate, LeadUpdate, LeadResponse, LeadDetailResponse,
    LeadStageCreate, LeadStageResponse, LeadImportResult
)
from backend.app.services.lead_service import (
    create_lead, parse_and_import_leads, get_lead_details, check_duplicate_lead
)
from backend.app.security.dependencies import get_current_user, require_roles, get_tenant_company_id

router = APIRouter(prefix="/leads", tags=["Leads"])

@router.get("/stages", response_model=List[LeadStageResponse])
def list_lead_stages(
    company_id: str = Depends(get_tenant_company_id),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    return db.query(LeadStage).filter(
        LeadStage.company_id == company_id
    ).order_by(LeadStage.order_index).all()

@router.post("/stages", response_model=LeadStageResponse)
def create_lead_stage(
    stage_in: LeadStageCreate,
    company_id: str = Depends(get_tenant_company_id),
    admin: User = Depends(require_roles("admin")),
    db: Session = Depends(get_db)
):
    existing = db.query(LeadStage).filter(
        LeadStage.company_id == company_id,
        LeadStage.name.ilike(stage_in.name.strip())
    ).first()
    if existing:
        raise HTTPException(status_code=400, detail="A stage with this name already exists.")

    stage = LeadStage(
        company_id=company_id,
        name=stage_in.name.strip(),
        color_hex=stage_in.color_hex,
        order_index=stage_in.order_index,
        is_terminal=stage_in.is_terminal
    )
    db.add(stage)
    db.commit()
    db.refresh(stage)
    return stage

@router.get("", response_model=List[LeadResponse])
def list_leads(
    search: Optional[str] = None,
    stage_id: Optional[str] = None,
    source: Optional[str] = None,
    assigned_to: Optional[str] = None,
    unassigned_only: bool = False,
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=500),
    company_id: str = Depends(get_tenant_company_id),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    query = db.query(Lead).filter(
        Lead.company_id == company_id,
        Lead.is_deleted == False
    )

    # Telecaller sees ONLY their own assigned leads
    if current_user.role == "telecaller":
        query = query.filter(Lead.assigned_to == current_user.id)
    else:
        # Admin / Manager filters
        if unassigned_only:
            query = query.filter(Lead.assigned_to.is_(None))
        elif assigned_to:
            query = query.filter(Lead.assigned_to == assigned_to)

    if stage_id:
        query = query.filter(Lead.stage_id == stage_id)

    if source:
        query = query.filter(Lead.source == source)

    if search:
        search_fmt = f"%{search.strip()}%"
        query = query.filter(
            or_(
                Lead.first_name.ilike(search_fmt),
                Lead.last_name.ilike(search_fmt),
                Lead.phone.ilike(search_fmt),
                Lead.email.ilike(search_fmt),
                Lead.city.ilike(search_fmt)
            )
        )

    leads = query.order_by(desc(Lead.created_at)).offset(skip).limit(limit).all()

    results = []
    for l in leads:
        results.append(LeadResponse(
            id=l.id,
            first_name=l.first_name,
            last_name=l.last_name or "",
            phone=l.phone,
            alternate_phone=l.alternate_phone,
            email=l.email,
            city=l.city,
            source=l.source,
            stage_id=l.stage_id,
            stage_name=l.stage.name if l.stage else "New",
            stage_color=l.stage.color_hex if l.stage else "#3B82F6",
            assigned_to=l.assigned_to,
            assigned_to_name=l.assignee.full_name if l.assignee else "Unassigned",
            total_calls_count=l.total_calls_count,
            last_call_at=l.last_call_at,
            next_followup_at=l.next_followup_at,
            tags=l.tags or [],
            created_at=l.created_at,
            updated_at=l.updated_at
        ))
    return results

@router.post("", response_model=LeadResponse)
def add_lead_manually(
    lead_in: LeadCreate,
    company_id: str = Depends(get_tenant_company_id),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    try:
        # If telecaller creates lead, auto-assign to themselves
        if current_user.role == "telecaller":
            lead_in.assigned_to = current_user.id

        lead = create_lead(db, company_id, lead_in, current_user.id)
        return LeadResponse(
            id=lead.id,
            first_name=lead.first_name,
            last_name=lead.last_name or "",
            phone=lead.phone,
            alternate_phone=lead.alternate_phone,
            email=lead.email,
            city=lead.city,
            source=lead.source,
            stage_id=lead.stage_id,
            stage_name=lead.stage.name if lead.stage else "New",
            stage_color=lead.stage.color_hex if lead.stage else "#3B82F6",
            assigned_to=lead.assigned_to,
            assigned_to_name=lead.assignee.full_name if lead.assignee else "Unassigned",
            total_calls_count=lead.total_calls_count,
            last_call_at=lead.last_call_at,
            next_followup_at=lead.next_followup_at,
            tags=lead.tags or [],
            created_at=lead.created_at,
            updated_at=lead.updated_at
        )
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))

@router.get("/check-duplicate")
def check_duplicate_phone(
    phone: str,
    exclude_id: Optional[str] = None,
    company_id: str = Depends(get_tenant_company_id),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    duplicate = check_duplicate_lead(db, company_id, phone, exclude_id)
    if duplicate:
        return {
            "is_duplicate": True,
            "existing_lead_id": duplicate.id,
            "existing_lead_name": f"{duplicate.first_name} {duplicate.last_name or ''}".strip(),
            "assigned_to_name": duplicate.assignee.full_name if duplicate.assignee else "Unassigned"
        }
    return {"is_duplicate": False}

@router.get("/{lead_id}", response_model=Dict[str, Any])
def get_lead_full_history(
    lead_id: str,
    company_id: str = Depends(get_tenant_company_id),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    details = get_lead_details(db, company_id, lead_id)
    if not details:
        raise HTTPException(status_code=404, detail="Lead not found.")

    # Telecaller can view only their assigned leads
    if current_user.role == "telecaller" and details["assigned_to"] != current_user.id:
        raise HTTPException(status_code=403, detail="You do not have permission to view this lead.")

    return details

@router.put("/{lead_id}", response_model=LeadResponse)
def update_lead(
    lead_id: str,
    lead_up: LeadUpdate,
    company_id: str = Depends(get_tenant_company_id),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    lead = db.query(Lead).filter(
        Lead.id == lead_id,
        Lead.company_id == company_id,
        Lead.is_deleted == False
    ).first()
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found.")

    if current_user.role == "telecaller" and lead.assigned_to != current_user.id:
        raise HTTPException(status_code=403, detail="Permission denied.")

    if lead_up.first_name is not None:
        lead.first_name = lead_up.first_name
    if lead_up.last_name is not None:
        lead.last_name = lead_up.last_name
    if lead_up.phone is not None:
        # Check duplicate
        dup = check_duplicate_lead(db, company_id, lead_up.phone, exclude_lead_id=lead.id)
        if dup:
            raise HTTPException(status_code=409, detail=f"Phone number already exists on lead {dup.id}")
        lead.phone = lead_up.phone
    if lead_up.city is not None:
        lead.city = lead_up.city
    if lead_up.email is not None:
        lead.email = lead_up.email
    if lead_up.stage_id is not None:
        lead.stage_id = lead_up.stage_id
    if lead_up.tags is not None:
        lead.tags = lead_up.tags
    if lead_up.custom_fields is not None:
        lead.custom_fields = lead_up.custom_fields

    db.commit()
    db.refresh(lead)

    return LeadResponse(
        id=lead.id,
        first_name=lead.first_name,
        last_name=lead.last_name or "",
        phone=lead.phone,
        alternate_phone=lead.alternate_phone,
        email=lead.email,
        city=lead.city,
        source=lead.source,
        stage_id=lead.stage_id,
        stage_name=lead.stage.name if lead.stage else None,
        stage_color=lead.stage.color_hex if lead.stage else "#3B82F6",
        assigned_to=lead.assigned_to,
        assigned_to_name=lead.assignee.full_name if lead.assignee else "Unassigned",
        total_calls_count=lead.total_calls_count,
        last_call_at=lead.last_call_at,
        next_followup_at=lead.next_followup_at,
        tags=lead.tags or [],
        created_at=lead.created_at,
        updated_at=lead.updated_at
    )

@router.post("/import/preview")
async def preview_import_file(
    file: UploadFile = File(...),
    company_id: str = Depends(get_tenant_company_id),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Step 1 & 2: Parse file, return headers, row count, first 20 preview rows and auto-detected column mappings."""
    import io, csv, openpyxl, re
    contents = await file.read()
    filename = (file.filename or "upload.csv").lower()

    rows_data = []
    headers = []

    if filename.endswith(".csv"):
        text = contents.decode("utf-8-sig", errors="replace")
        reader = csv.reader(io.StringIO(text))
        all_rows = [r for r in reader if any(c.strip() for c in r)]
        if not all_rows:
            raise HTTPException(status_code=400, detail="The uploaded CSV file is empty.")
        headers = [h.strip() for h in all_rows[0]]
        for row in all_rows[1:]:
            row_dict = {headers[i]: (row[i].strip() if i < len(row) else "") for i in range(len(headers))}
            rows_data.append(row_dict)
    elif filename.endswith((".xlsx", ".xls")):
        wb = openpyxl.load_workbook(io.BytesIO(contents), data_only=True)
        sheet = wb.active
        raw_rows = list(sheet.iter_rows(values_only=True))
        if not raw_rows:
            raise HTTPException(status_code=400, detail="The uploaded Excel sheet is empty.")
        headers = [str(c).strip() if c is not None else f"Column_{i+1}" for i, c in enumerate(raw_rows[0])]
        for row in raw_rows[1:]:
            if any(c is not None and str(c).strip() for c in row):
                row_dict = {headers[i]: (str(row[i]).strip() if i < len(row) and row[i] is not None else "") for i in range(len(headers))}
                rows_data.append(row_dict)
    else:
        raise HTTPException(status_code=400, detail="Unsupported format. Please upload .xlsx, .xls, or .csv")

    if not rows_data:
        raise HTTPException(status_code=400, detail="No data rows found in file.")

    # Auto-detect column mappings
    auto_mapping = {
        "name": "",
        "phone": "",
        "alternate_phone": "",
        "city": "",
        "source": "",
        "notes": ""
    }

    for h in headers:
        hl = h.lower()
        if not auto_mapping["phone"] and any(k in hl for k in ["phone", "mobile", "contact", "cell", "number", "tel"]):
            auto_mapping["phone"] = h
        elif not auto_mapping["name"] and any(k in hl for k in ["name", "full_name", "first_name", "client", "customer", "lead"]):
            auto_mapping["name"] = h
        elif not auto_mapping["alternate_phone"] and any(k in hl for k in ["alt", "secondary", "other"]):
            auto_mapping["alternate_phone"] = h
        elif not auto_mapping["city"] and any(k in hl for k in ["city", "location", "town", "state"]):
            auto_mapping["city"] = h
        elif not auto_mapping["source"] and any(k in hl for k in ["source", "campaign", "channel"]):
            auto_mapping["source"] = h
        elif not auto_mapping["notes"] and any(k in hl for k in ["note", "remark", "comment"]):
            auto_mapping["notes"] = h

    # Pre-validate sample rows
    preview_rows = rows_data[:20]
    total_rows = len(rows_data)

    return {
        "filename": file.filename,
        "total_rows": total_rows,
        "headers": headers,
        "auto_mapping": auto_mapping,
        "preview_rows": preview_rows
    }

@router.post("/import/execute")
async def execute_lead_import(
    file: UploadFile = File(...),
    column_mapping_json: str = Form(...),
    duplicate_handling: str = Form("skip"), # "skip", "update", "allow"
    assignment_mode: str = Form("unassigned"), # "unassigned", "single", "round_robin", "custom"
    assigned_user_id: Optional[str] = Form(None),
    assigned_user_ids_json: Optional[str] = Form(None), # JSON list of IDs
    custom_counts_json: Optional[str] = Form(None), # JSON dict {user_id: count}
    default_stage_id: Optional[str] = Form(None),
    source_tag: Optional[str] = Form("Bulk Upload"),
    batch_name: Optional[str] = Form(None),
    company_id: str = Depends(get_tenant_company_id),
    current_user: User = Depends(require_roles("admin", "manager")),
    db: Session = Depends(get_db)
):
    """Step 4: Execute bulk import with duplicate detection, allocation, history logging, and error tracking."""
    import io, csv, openpyxl, re
    from backend.app.models.lead import LeadImportHistory
    from backend.app.models.notification import Notification

    try:
        column_mapping = json.loads(column_mapping_json)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid column mapping format.")

    assigned_user_ids = []
    if assigned_user_ids_json:
        try:
            assigned_user_ids = json.loads(assigned_user_ids_json)
        except Exception:
            pass

    custom_counts = {}
    if custom_counts_json:
        try:
            custom_counts = json.loads(custom_counts_json)
        except Exception:
            pass

    contents = await file.read()
    filename = (file.filename or "import.csv").lower()

    rows_data = []
    if filename.endswith(".csv"):
        text = contents.decode("utf-8-sig", errors="replace")
        reader = csv.reader(io.StringIO(text))
        all_rows = [r for r in reader if any(c.strip() for c in r)]
        if all_rows:
            headers = [h.strip() for h in all_rows[0]]
            for row in all_rows[1:]:
                row_dict = {headers[i]: (row[i].strip() if i < len(row) else "") for i in range(len(headers))}
                rows_data.append(row_dict)
    else:
        wb = openpyxl.load_workbook(io.BytesIO(contents), data_only=True)
        sheet = wb.active
        raw_rows = list(sheet.iter_rows(values_only=True))
        if raw_rows:
            headers = [str(c).strip() if c is not None else f"Column_{i+1}" for i, c in enumerate(raw_rows[0])]
            for row in raw_rows[1:]:
                if any(c is not None and str(c).strip() for c in row):
                    row_dict = {headers[i]: (str(row[i]).strip() if i < len(row) and row[i] is not None else "") for i in range(len(headers))}
                    rows_data.append(row_dict)

    # Resolve default stage
    stage_id = default_stage_id
    if not stage_id:
        def_st = db.query(LeadStage).filter(LeadStage.company_id == company_id, LeadStage.name == "New").first()
        if not def_st:
            def_st = LeadStage(company_id=company_id, name="New", color_hex="#3B82F6", order_index=0)
            db.add(def_st)
            db.flush()
        stage_id = def_st.id

    # Create import history record
    import_batch = LeadImportHistory(
        company_id=company_id,
        uploaded_by=current_user.id,
        file_name=file.filename or "upload.csv",
        batch_name=batch_name or f"Import {datetime.now().strftime('%d %b %Y %H:%M')}",
        total_rows=len(rows_data),
        imported_count=0,
        duplicates_count=0,
        failed_count=0,
        status="processing",
        error_report=[],
        imported_lead_ids=[]
    )
    db.add(import_batch)
    db.flush()

    name_col = column_mapping.get("name", "")
    phone_col = column_mapping.get("phone", "")
    alt_phone_col = column_mapping.get("alternate_phone", "")
    city_col = column_mapping.get("city", "")
    source_col = column_mapping.get("source", "")
    notes_col = column_mapping.get("notes", "")

    if not phone_col:
        raise HTTPException(status_code=400, detail="Phone number column mapping is required.")

    seen_phones_in_batch = set()
    errors = []
    created_lead_ids = []
    imported_count = 0
    duplicate_count = 0
    failed_count = 0

    # Build assignees pool for round robin or custom count
    round_robin_index = 0
    custom_count_tracker = {uid: 0 for uid in custom_counts}

    for idx, row in enumerate(rows_data, start=2):
        raw_phone = row.get(phone_col, "").strip()
        digits = re.sub(r"[^\d+]", "", raw_phone)
        if digits.startswith("+91"):
            clean_phone = digits[3:]
        elif digits.startswith("91") and len(digits) == 12:
            clean_phone = digits[2:]
        elif digits.startswith("0") and len(digits) == 11:
            clean_phone = digits[1:]
        else:
            clean_phone = digits

        # Validation: phone must be 10 digits
        if not clean_phone or len(clean_phone) < 7:
            failed_count += 1
            errors.append({
                "row": idx,
                "name": row.get(name_col, ""),
                "phone": raw_phone,
                "reason": "Missing or invalid phone number (less than 7 digits)"
            })
            continue

        raw_name = row.get(name_col, "").strip() if name_col else ""
        first_name = raw_name if raw_name else f"Lead-{clean_phone[-4:]}"
        city = row.get(city_col, "").strip() if city_col else None
        alt_phone = row.get(alt_phone_col, "").strip() if alt_phone_col else None
        row_source = row.get(source_col, "").strip() if source_col else (source_tag or "Excel Import")
        row_notes = row.get(notes_col, "").strip() if notes_col else None

        # Check duplicate within file
        if clean_phone in seen_phones_in_batch:
            duplicate_count += 1
            errors.append({
                "row": idx,
                "name": first_name,
                "phone": clean_phone,
                "reason": "Duplicate phone number inside uploaded file"
            })
            continue

        seen_phones_in_batch.add(clean_phone)

        # Check duplicate in database
        existing = db.query(Lead).filter(
            Lead.company_id == company_id,
            Lead.is_deleted == False,
            Lead.phone == clean_phone
        ).first()

        if existing:
            if duplicate_handling == "skip":
                duplicate_count += 1
                errors.append({
                    "row": idx,
                    "name": first_name,
                    "phone": clean_phone,
                    "reason": f"Already exists in CRM (Lead ID: {existing.id})"
                })
                continue
            elif duplicate_handling == "update":
                existing.first_name = first_name
                if city:
                    existing.city = city
                if alt_phone:
                    existing.alternate_phone = alt_phone
                if row_notes:
                    existing.custom_fields = {**(existing.custom_fields or {}), "import_notes": row_notes}
                imported_count += 1
                created_lead_ids.append(existing.id)
                continue
            # if "allow", we proceed but phone uniqueness constraint requires unique phone per tenant
            # so we skip with explicit error to preserve DB constraint integrity
            duplicate_count += 1
            errors.append({
                "row": idx,
                "name": first_name,
                "phone": clean_phone,
                "reason": f"Company policy constraint: Duplicate phone already in CRM"
            })
            continue

        # Determine assignment
        target_agent_id = None
        if assignment_mode == "single" and assigned_user_id:
            target_agent_id = assigned_user_id
        elif assignment_mode == "round_robin" and assigned_user_ids:
            target_agent_id = assigned_user_ids[round_robin_index % len(assigned_user_ids)]
            round_robin_index += 1
        elif assignment_mode == "custom" and custom_counts:
            for uid, max_ct in custom_counts.items():
                if custom_count_tracker.get(uid, 0) < max_ct:
                    target_agent_id = uid
                    custom_count_tracker[uid] += 1
                    break

        new_lead = Lead(
            company_id=company_id,
            first_name=first_name,
            last_name="",
            phone=clean_phone,
            alternate_phone=alt_phone,
            city=city,
            source=row_source,
            stage_id=stage_id,
            assigned_to=target_agent_id,
            assigned_at=datetime.utcnow() if target_agent_id else None,
            import_batch_id=import_batch.id,
            custom_fields={"import_notes": row_notes} if row_notes else {}
        )
        db.add(new_lead)
        db.flush()

        if target_agent_id:
            alloc = LeadAllocation(
                company_id=company_id,
                lead_id=new_lead.id,
                assigned_by=current_user.id,
                from_user_id=None,
                to_user_id=target_agent_id,
                transfer_reason=f"Bulk Import Batch: {import_batch.batch_name}"
            )
            db.add(alloc)

        created_lead_ids.append(new_lead.id)
        imported_count += 1

    # Update history record
    import_batch.imported_count = imported_count
    import_batch.duplicates_count = duplicate_count
    import_batch.failed_count = failed_count
    import_batch.status = "completed"
    import_batch.error_report = errors
    import_batch.imported_lead_ids = created_lead_ids

    # Create in-app notification
    notif = Notification(
        company_id=company_id,
        user_id=current_user.id,
        title="Excel Import Completed",
        message=f"Batch '{import_batch.batch_name}' finished: {imported_count} imported, {duplicate_count} skipped, {failed_count} failed.",
        type="import_completed"
    )
    db.add(notif)
    db.commit()

    return {
        "batch_id": import_batch.id,
        "batch_name": import_batch.batch_name,
        "total_rows": len(rows_data),
        "imported": imported_count,
        "duplicates": duplicate_count,
        "failed": failed_count,
        "error_report": errors[:50] # Top 50 errors in response
    }

@router.get("/import/sample-template")
def download_sample_template(
    format: str = Query("xlsx", pattern="^(xlsx|csv)$"),
    company_id: str = Depends(get_tenant_company_id),
    current_user: User = Depends(get_current_user)
):
    """Provides downloadable sample Excel / CSV template for bulk upload."""
    import io, csv, openpyxl
    from fastapi.responses import StreamingResponse

    headers = ["Name", "Phone", "Alternate Phone", "City", "Source", "Notes"]
    sample_rows = [
        ["Rahul Sharma", "9876543210", "9876500000", "Mumbai", "Website", "Interested in 3-month plan"],
        ["Pooja Verma", "9811122233", "", "Delhi", "Referral", "Wants morning call"],
        ["Amit Roy", "9922334455", "9922334456", "Bangalore", "Expo", "High priority lead"],
    ]

    if format == "csv":
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(headers)
        writer.writerows(sample_rows)
        output.seek(0)
        return StreamingResponse(
            io.BytesIO(output.getvalue().encode("utf-8-sig")),
            media_type="text/csv",
            headers={"Content-Disposition": "attachment; filename=crm_lead_import_sample.csv"}
        )
    else:
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "Leads Template"
        ws.append(headers)
        for r in sample_rows:
            ws.append(r)
        
        # Style header row in clean blue
        from openpyxl.styles import Font, PatternFill
        blue_fill = PatternFill(start_color="2563EB", end_color="2563EB", fill_type="solid")
        white_font = Font(color="FFFFFF", bold=True)
        for col_idx in range(1, len(headers) + 1):
            cell = ws.cell(row=1, column=col_idx)
            cell.fill = blue_fill
            cell.font = white_font

        out_stream = io.BytesIO()
        wb.save(out_stream)
        out_stream.seek(0)
        return StreamingResponse(
            out_stream,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={"Content-Disposition": "attachment; filename=crm_lead_import_sample.xlsx"}
        )

@router.get("/import/history")
def list_import_history(
    company_id: str = Depends(get_tenant_company_id),
    current_user: User = Depends(require_roles("admin", "manager")),
    db: Session = Depends(get_db)
):
    """Returns past bulk upload batches with statistics."""
    from backend.app.models.lead import LeadImportHistory
    history = db.query(LeadImportHistory).filter(
        LeadImportHistory.company_id == company_id
    ).order_by(desc(LeadImportHistory.created_at)).all()

    return [
        {
            "id": h.id,
            "file_name": h.file_name,
            "batch_name": h.batch_name,
            "total_rows": h.total_rows,
            "imported_count": h.imported_count,
            "duplicates_count": h.duplicates_count,
            "failed_count": h.failed_count,
            "status": h.status,
            "has_errors": len(h.error_report or []) > 0,
            "created_at": h.created_at.strftime("%Y-%m-%d %H:%M:%S") if h.created_at else "",
            "uploaded_by_name": h.uploader.full_name if h.uploader else "System"
        }
        for h in history
    ]

@router.get("/import/history/{history_id}/error-report")
def download_error_report(
    history_id: str,
    company_id: str = Depends(get_tenant_company_id),
    current_user: User = Depends(require_roles("admin", "manager")),
    db: Session = Depends(get_db)
):
    """Downloads an Excel file detailing failed and skipped rows with specific reasons."""
    import io, openpyxl
    from openpyxl.styles import Font, PatternFill
    from fastapi.responses import StreamingResponse
    from backend.app.models.lead import LeadImportHistory

    batch = db.query(LeadImportHistory).filter(
        LeadImportHistory.id == history_id,
        LeadImportHistory.company_id == company_id
    ).first()
    if not batch:
        raise HTTPException(status_code=404, detail="Batch history not found.")

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Import Errors"
    headers = ["Excel Row", "Name", "Phone", "Failure Reason"]
    ws.append(headers)

    header_fill = PatternFill(start_color="DC2626", end_color="DC2626", fill_type="solid")
    header_font = Font(color="FFFFFF", bold=True)
    for col_idx in range(1, len(headers) + 1):
        cell = ws.cell(row=1, column=col_idx)
        cell.fill = header_fill
        cell.font = header_font

    for item in (batch.error_report or []):
        ws.append([
            item.get("row", ""),
            item.get("name", ""),
            item.get("phone", ""),
            item.get("reason", "")
        ])

    out = io.BytesIO()
    wb.save(out)
    out.seek(0)

    filename = f"error_report_{batch.file_name}.xlsx"
    return StreamingResponse(
        out,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )

@router.post("/import/history/{history_id}/undo")
def undo_import_batch(
    history_id: str,
    company_id: str = Depends(get_tenant_company_id),
    admin: User = Depends(require_roles("admin")),
    db: Session = Depends(get_db)
):
    """Admin-only: Deletes all leads created in a specific import batch."""
    from backend.app.models.lead import LeadImportHistory

    batch = db.query(LeadImportHistory).filter(
        LeadImportHistory.id == history_id,
        LeadImportHistory.company_id == company_id
    ).first()
    if not batch:
        raise HTTPException(status_code=404, detail="Batch history not found.")

    if batch.status == "undone":
        raise HTTPException(status_code=400, detail="This batch has already been undone.")

    # Delete all leads tagged with this batch ID
    deleted_count = db.query(Lead).filter(
        Lead.company_id == company_id,
        Lead.import_batch_id == batch.id
    ).delete(synchronize_session=False)

    batch.status = "undone"
    db.commit()

    return {
        "status": "undone",
        "batch_id": batch.id,
        "deleted_leads_count": deleted_count
    }

@router.get("/export/excel")
def export_leads_excel(
    search: Optional[str] = None,
    stage_id: Optional[str] = None,
    assigned_to: Optional[str] = None,
    company_id: str = Depends(get_tenant_company_id),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Exports filtered leads catalog as openpyxl Excel spreadsheet."""
    import io, openpyxl
    from openpyxl.styles import Font, PatternFill
    from fastapi.responses import StreamingResponse

    query = db.query(Lead).filter(Lead.company_id == company_id, Lead.is_deleted == False)
    if current_user.role == "telecaller":
        query = query.filter(Lead.assigned_to == current_user.id)
    elif assigned_to:
        query = query.filter(Lead.assigned_to == assigned_to)
    if stage_id:
        query = query.filter(Lead.stage_id == stage_id)
    if search:
        s = f"%{search.strip()}%"
        query = query.filter(or_(Lead.first_name.ilike(s), Lead.phone.ilike(s), Lead.city.ilike(s)))

    leads = query.order_by(desc(Lead.created_at)).all()

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Leads"
    headers = ["Lead ID", "Name", "Phone", "Alt Phone", "City", "Source", "Stage", "Assigned To", "Total Calls", "Last Call", "Created At"]
    ws.append(headers)

    header_fill = PatternFill(start_color="2563EB", end_color="2563EB", fill_type="solid")
    header_font = Font(color="FFFFFF", bold=True)
    for col_idx in range(1, len(headers) + 1):
        cell = ws.cell(row=1, column=col_idx)
        cell.fill = header_fill
        cell.font = header_font

    for l in leads:
        ws.append([
            l.id,
            f"{l.first_name} {l.last_name or ''}".strip(),
            l.phone,
            l.alternate_phone or "",
            l.city or "",
            l.source or "",
            l.stage.name if l.stage else "",
            l.assignee.full_name if l.assignee else "Unassigned",
            l.total_calls_count,
            l.last_call_at.strftime("%Y-%m-%d %H:%M") if l.last_call_at else "",
            l.created_at.strftime("%Y-%m-%d %H:%M") if l.created_at else ""
        ])

    out = io.BytesIO()
    wb.save(out)
    out.seek(0)

    return StreamingResponse(
        out,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": "attachment; filename=leads_export.xlsx"}
    )

@router.get("/export/csv")
def export_leads_csv(
    search: Optional[str] = None,
    stage_id: Optional[str] = None,
    assigned_to: Optional[str] = None,
    company_id: str = Depends(get_tenant_company_id),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Exports filtered leads catalog as CSV."""
    import io, csv
    from fastapi.responses import StreamingResponse

    query = db.query(Lead).filter(Lead.company_id == company_id, Lead.is_deleted == False)
    if current_user.role == "telecaller":
        query = query.filter(Lead.assigned_to == current_user.id)
    elif assigned_to:
        query = query.filter(Lead.assigned_to == assigned_to)
    if stage_id:
        query = query.filter(Lead.stage_id == stage_id)
    if search:
        s = f"%{search.strip()}%"
        query = query.filter(or_(Lead.first_name.ilike(s), Lead.phone.ilike(s), Lead.city.ilike(s)))

    leads = query.order_by(desc(Lead.created_at)).all()

    out = io.StringIO()
    writer = csv.writer(out)
    writer.writerow(["Lead ID", "Name", "Phone", "Alt Phone", "City", "Source", "Stage", "Assigned To", "Total Calls", "Last Call", "Created At"])
    for l in leads:
        writer.writerow([
            l.id,
            f"{l.first_name} {l.last_name or ''}".strip(),
            l.phone,
            l.alternate_phone or "",
            l.city or "",
            l.source or "",
            l.stage.name if l.stage else "",
            l.assignee.full_name if l.assignee else "Unassigned",
            l.total_calls_count,
            l.last_call_at.strftime("%Y-%m-%d %H:%M") if l.last_call_at else "",
            l.created_at.strftime("%Y-%m-%d %H:%M") if l.created_at else ""
        ])

    out.seek(0)
    return StreamingResponse(
        io.BytesIO(out.getvalue().encode("utf-8-sig")),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=leads_export.csv"}
    )
