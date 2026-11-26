from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File
from sqlalchemy.orm import Session
from typing import List, Optional
from datetime import datetime, timezone, date

from backend.app.database import get_db
from backend.app.models.user import User, TelecallerShift, BreakLog
from backend.app.models.company import Company
from backend.app.models.lead import Lead
from backend.app.models.call import CallLog
from backend.app.schemas.user import (
    EmployeeCreate, EmployeeUpdate, EmployeeResponse, StatusUpdateRequest
)
from backend.app.schemas.auth import PasswordResetRequest
from backend.app.security.auth import get_password_hash
from backend.app.security.dependencies import get_current_user, require_roles, get_tenant_company_id

router = APIRouter(prefix="/employees", tags=["Employee Management"])

@router.get("", response_model=List[EmployeeResponse])
def list_employees(
    company_id: str = Depends(get_tenant_company_id),
    current_user: User = Depends(require_roles("admin", "manager")),
    db: Session = Depends(get_db)
):
    users = db.query(User).filter(User.company_id == company_id).order_by(User.full_name).all()
    results = []
    today = date.today()

    for u in users:
        leads_count = db.query(Lead).filter(
            Lead.company_id == company_id,
            Lead.assigned_to == u.id,
            Lead.is_deleted == False
        ).count()

        shift = db.query(TelecallerShift).filter(
            TelecallerShift.company_id == company_id,
            TelecallerShift.user_id == u.id,
            TelecallerShift.shift_date == today
        ).first()

        results.append(EmployeeResponse(
            id=u.id,
            full_name=u.full_name,
            email=u.email,
            phone=u.phone,
            role=u.role,
            agent_status=u.agent_status,
            status_updated_at=u.status_updated_at,
            telephony_agent_id=u.telephony_agent_id,
            is_active=u.is_active,
            assigned_leads_count=leads_count,
            today_calls_count=shift.total_calls_handled if shift else 0,
            today_talk_time_sec=shift.total_talk_time_sec if shift else 0,
            created_at=u.created_at
        ))
    return results

@router.post("", response_model=EmployeeResponse)
def create_employee(
    emp_in: EmployeeCreate,
    company_id: str = Depends(get_tenant_company_id),
    admin: User = Depends(require_roles("admin")),
    db: Session = Depends(get_db)
):
    # Check plan limit
    company = db.query(Company).filter(Company.id == company_id).first()
    current_emp_count = db.query(User).filter(User.company_id == company_id).count()
    if company.plan and current_emp_count >= company.plan.max_employees:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Employee limit of {company.plan.max_employees} reached for your plan. Please upgrade your plan."
        )

    # Check email duplicate inside company
    existing = db.query(User).filter(
        User.company_id == company_id,
        User.email == emp_in.email.strip().lower()
    ).first()
    if existing:
        raise HTTPException(status_code=400, detail="Employee with this email already exists in your company.")

    new_emp = User(
        company_id=company_id,
        email=emp_in.email.strip().lower(),
        password_hash=get_password_hash(emp_in.password),
        full_name=emp_in.full_name.strip(),
        phone=emp_in.phone.strip(),
        role=emp_in.role,
        telephony_agent_id=emp_in.telephony_agent_id,
        agent_status="offline"
    )
    db.add(new_emp)
    db.commit()
    db.refresh(new_emp)

    return EmployeeResponse(
        id=new_emp.id,
        full_name=new_emp.full_name,
        email=new_emp.email,
        phone=new_emp.phone,
        role=new_emp.role,
        agent_status=new_emp.agent_status,
        status_updated_at=new_emp.status_updated_at,
        telephony_agent_id=new_emp.telephony_agent_id,
        is_active=new_emp.is_active,
        assigned_leads_count=0,
        today_calls_count=0,
        today_talk_time_sec=0,
        created_at=new_emp.created_at
    )

@router.put("/{employee_id}", response_model=EmployeeResponse)
def update_employee(
    employee_id: str,
    emp_update: EmployeeUpdate,
    company_id: str = Depends(get_tenant_company_id),
    admin: User = Depends(require_roles("admin")),
    db: Session = Depends(get_db)
):
    user = db.query(User).filter(User.id == employee_id, User.company_id == company_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="Employee not found.")

    if emp_update.full_name is not None:
        user.full_name = emp_update.full_name.strip()
    if emp_update.email is not None:
        user.email = emp_update.email.strip().lower()
    if emp_update.phone is not None:
        user.phone = emp_update.phone.strip()
    if emp_update.role is not None:
        user.role = emp_update.role
    if emp_update.telephony_agent_id is not None:
        user.telephony_agent_id = emp_update.telephony_agent_id
    if emp_update.is_active is not None:
        user.is_active = emp_update.is_active

    db.commit()
    db.refresh(user)

    leads_count = db.query(Lead).filter(
        Lead.company_id == company_id,
        Lead.assigned_to == user.id,
        Lead.is_deleted == False
    ).count()

    return EmployeeResponse(
        id=user.id,
        full_name=user.full_name,
        email=user.email,
        phone=user.phone,
        role=user.role,
        agent_status=user.agent_status,
        status_updated_at=user.status_updated_at,
        telephony_agent_id=user.telephony_agent_id,
        is_active=user.is_active,
        assigned_leads_count=leads_count,
        today_calls_count=0,
        today_talk_time_sec=0,
        created_at=user.created_at
    )

@router.post("/{employee_id}/reset-password")
def reset_employee_password(
    employee_id: str,
    body: PasswordResetRequest,
    company_id: str = Depends(get_tenant_company_id),
    admin: User = Depends(require_roles("admin")),
    db: Session = Depends(get_db)
):
    user = db.query(User).filter(User.id == employee_id, User.company_id == company_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="Employee not found.")

    user.password_hash = get_password_hash(body.new_password)
    db.commit()
    return {"status": "success", "message": f"Password reset successfully for {user.full_name}."}

@router.post("/status")
def update_telecaller_status(
    status_req: StatusUpdateRequest,
    current_user: User = Depends(get_current_user),
    company_id: str = Depends(get_tenant_company_id),
    db: Session = Depends(get_db)
):
    """
    Employee updates their presence status (idle, break, offline).
    Tracks break logs and shift duration.
    """
    now = datetime.now(timezone.utc)
    old_status = current_user.agent_status
    new_status = status_req.status

    current_user.agent_status = new_status
    current_user.status_updated_at = now

    today_date = now.date()
    shift = db.query(TelecallerShift).filter(
        TelecallerShift.company_id == company_id,
        TelecallerShift.user_id == current_user.id,
        TelecallerShift.shift_date == today_date
    ).first()

    if not shift:
        shift = TelecallerShift(
            company_id=company_id,
            user_id=current_user.id,
            shift_date=today_date,
            clock_in_at=now
        )
        db.add(shift)
        db.flush()

    # If transitioning to break, record break start
    if new_status == "break":
        break_log = BreakLog(
            shift_id=shift.id,
            break_reason=status_req.break_reason or "General Break",
            started_at=now
        )
        db.add(break_log)
    elif old_status == "break" and new_status != "break":
        # Closing active break
        active_break = db.query(BreakLog).filter(
            BreakLog.shift_id == shift.id,
            BreakLog.ended_at.is_(None)
        ).order_by(BreakLog.started_at.desc()).first()
        if active_break:
            active_break.ended_at = now
            duration = int((now - active_break.started_at.replace(tzinfo=timezone.utc)).total_seconds())
            active_break.duration_seconds = max(0, duration)
            shift.total_break_time_sec = (shift.total_break_time_sec or 0) + duration

    db.commit()
    return {
        "status": "success",
        "agent_status": current_user.agent_status,
        "updated_at": current_user.status_updated_at
    }

@router.post("/bulk-import")
async def bulk_import_employees(
    file: UploadFile = File(...),
    company_id: str = Depends(get_tenant_company_id),
    admin: User = Depends(require_roles("admin")),
    db: Session = Depends(get_db)
):
    """Bulk adds employees via Excel (.xlsx) or CSV."""
    import io, csv, openpyxl, re
    from fastapi import UploadFile, File
    contents = await file.read()
    filename = (file.filename or "employees.csv").lower()

    rows = []
    if filename.endswith(".csv"):
        text = contents.decode("utf-8-sig", errors="replace")
        reader = csv.DictReader(io.StringIO(text))
        rows = list(reader)
    else:
        wb = openpyxl.load_workbook(io.BytesIO(contents), data_only=True)
        sheet = wb.active
        all_vals = list(sheet.iter_rows(values_only=True))
        if all_vals:
            headers = [str(c).strip().lower() if c else f"col_{i}" for i, c in enumerate(all_vals[0])]
            for r in all_vals[1:]:
                if any(r):
                    rows.append({headers[i]: str(r[i]).strip() if i < len(r) and r[i] is not None else "" for i in range(len(headers))})

    imported = 0
    failed = 0
    errors = []

    for idx, r in enumerate(rows, start=2):
        name = r.get("name") or r.get("full_name") or r.get("employee_name") or ""
        email = (r.get("email") or "").strip().lower()
        phone = r.get("phone") or r.get("mobile") or ""
        role = (r.get("role") or "telecaller").strip().lower()
        pwd = r.get("password") or "Password@123"

        if not name or not email:
            failed += 1
            errors.append({"row": idx, "reason": "Name and Email are mandatory."})
            continue

        existing = db.query(User).filter(User.company_id == company_id, User.email == email).first()
        if existing:
            failed += 1
            errors.append({"row": idx, "reason": f"Email '{email}' already registered."})
            continue

        valid_roles = ["telecaller", "manager", "admin"]
        assigned_role = role if role in valid_roles else "telecaller"

        emp = User(
            company_id=company_id,
            full_name=name,
            email=email,
            phone=phone,
            password_hash=get_password_hash(pwd),
            role=assigned_role,
            is_active=True
        )
        db.add(emp)
        imported += 1

    db.commit()
    return {
        "status": "success",
        "total_rows": len(rows),
        "imported": imported,
        "failed": failed,
        "errors": errors
    }

@router.get("/export/excel")
def export_employees_excel(
    company_id: str = Depends(get_tenant_company_id),
    admin: User = Depends(require_roles("admin")),
    db: Session = Depends(get_db)
):
    """Exports employee directory as openpyxl Excel spreadsheet."""
    import io, openpyxl
    from openpyxl.styles import Font, PatternFill
    from fastapi.responses import StreamingResponse

    users = db.query(User).filter(User.company_id == company_id).order_by(User.full_name).all()
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Employees Directory"

    headers = ["Employee ID", "Full Name", "Email", "Phone", "Role", "Status", "Active", "Created At"]
    ws.append(headers)

    header_fill = PatternFill(start_color="2563EB", end_color="2563EB", fill_type="solid")
    header_font = Font(color="FFFFFF", bold=True)
    for col_idx in range(1, len(headers) + 1):
        cell = ws.cell(row=1, column=col_idx)
        cell.fill = header_fill
        cell.font = header_font

    for u in users:
        ws.append([
            u.id,
            u.full_name,
            u.email,
            u.phone or "",
            u.role.upper(),
            u.agent_status.upper() if u.agent_status else "OFFLINE",
            "YES" if u.is_active else "NO",
            u.created_at.strftime("%Y-%m-%d") if u.created_at else ""
        ])

    out = io.BytesIO()
    wb.save(out)
    out.seek(0)
    return StreamingResponse(
        out,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": "attachment; filename=employees_directory.xlsx"}
    )

@router.get("/export/csv")
def export_employees_csv(
    company_id: str = Depends(get_tenant_company_id),
    admin: User = Depends(require_roles("admin")),
    db: Session = Depends(get_db)
):
    """Exports employee directory as CSV."""
    import io, csv
    from fastapi.responses import StreamingResponse

    users = db.query(User).filter(User.company_id == company_id).order_by(User.full_name).all()
    out = io.StringIO()
    writer = csv.writer(out)
    writer.writerow(["Employee ID", "Full Name", "Email", "Phone", "Role", "Status", "Active", "Created At"])
    for u in users:
        writer.writerow([
            u.id,
            u.full_name,
            u.email,
            u.phone or "",
            u.role.upper(),
            u.agent_status.upper() if u.agent_status else "OFFLINE",
            "YES" if u.is_active else "NO",
            u.created_at.strftime("%Y-%m-%d") if u.created_at else ""
        ])

    out.seek(0)
    return StreamingResponse(
        io.BytesIO(out.getvalue().encode("utf-8-sig")),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=employees_directory.csv"}
    )
