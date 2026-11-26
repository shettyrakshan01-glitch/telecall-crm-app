import io
import csv
from datetime import datetime, timezone, timedelta
from typing import Optional, List, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, Query, Response
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from sqlalchemy import desc
import openpyxl
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side

from backend.app.database import get_db
from backend.app.models.user import User, TelecallerShift
from backend.app.models.call import CallLog, CallDisposition
from backend.app.models.lead import Lead, LeadStage
from backend.app.security.dependencies import require_roles, get_tenant_company_id

router = APIRouter(prefix="/reports", tags=["Customizable Reports & Exports"])

def build_call_report_query(
    db: Session,
    company_id: str,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    agent_id: Optional[str] = None,
    status: Optional[str] = None,
    disposition_id: Optional[str] = None,
    source: Optional[str] = None
):
    query = db.query(CallLog).join(Lead).filter(CallLog.company_id == company_id)

    if start_date:
        try:
            s_dt = datetime.fromisoformat(start_date).replace(tzinfo=timezone.utc)
            query = query.filter(CallLog.started_at >= s_dt)
        except ValueError:
            pass

    if end_date:
        try:
            e_dt = datetime.fromisoformat(end_date).replace(tzinfo=timezone.utc) + timedelta(days=1)
            query = query.filter(CallLog.started_at < e_dt)
        except ValueError:
            pass

    if agent_id:
        query = query.filter(CallLog.telecaller_id == agent_id)

    if status:
        query = query.filter(CallLog.status == status)

    if disposition_id:
        query = query.filter(CallLog.disposition_id == disposition_id)

    if source:
        query = query.filter(Lead.source == source)

    return query.order_by(desc(CallLog.started_at))

@router.get("/calls", response_model=List[Dict[str, Any]])
def get_calls_report_data(
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    agent_id: Optional[str] = None,
    status: Optional[str] = None,
    disposition_id: Optional[str] = None,
    source: Optional[str] = None,
    limit: int = Query(200, ge=1, le=1000),
    company_id: str = Depends(get_tenant_company_id),
    current_user: User = Depends(require_roles("admin", "manager", "telecaller", "super_admin")),
    db: Session = Depends(get_db)
):
    # Telecaller agents only view their own calls
    if current_user.role == "telecaller":
        agent_id = current_user.id

    query = build_call_report_query(db, company_id, start_date, end_date, agent_id, status, disposition_id, source)
    calls = query.limit(limit).all()

    results = []
    for c in calls:
        if c.disposition:
            if c.disposition.code == "OTHER" and c.notes and c.notes.strip().lower() != "other":
                disp_display = f"Other: {c.notes.strip()}"
            else:
                disp_display = c.disposition.label
        else:
            disp_display = "Connected" if c.status == "connected" else "Completed"

        results.append({
            "id": c.id,
            "call_date": c.started_at.strftime("%Y-%m-%d %H:%M:%S") if c.started_at else "-",
            "lead_name": f"{c.lead.first_name} {c.lead.last_name or ''}".strip() if c.lead else "Customer",
            "lead_phone": c.callee_number,
            "lead_city": c.lead.city if c.lead else "-",
            "lead_source": c.lead.source if c.lead else "Manual",
            "telecaller_name": c.telecaller.full_name if c.telecaller else "Agent",
            "direction": c.direction,
            "status": c.status,
            "duration_seconds": c.duration_seconds,
            "talk_time_seconds": c.talk_time_seconds,
            "disposition_name": disp_display,
            "disposition_label": disp_display if c.disposition else "Pending",
            "notes": c.notes or "",
            "recording_url": c.recording_url or ""
        })
    return results

@router.get("/calls/export/csv")
def export_calls_csv(
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    agent_id: Optional[str] = None,
    status: Optional[str] = None,
    disposition_id: Optional[str] = None,
    source: Optional[str] = None,
    company_id: str = Depends(get_tenant_company_id),
    current_user: User = Depends(require_roles("admin", "manager")),
    db: Session = Depends(get_db)
):
    query = build_call_report_query(db, company_id, start_date, end_date, agent_id, status, disposition_id, source)
    calls = query.limit(5000).all()

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        "Call ID", "Date & Time", "Customer Name", "Customer Phone",
        "City", "Lead Source", "Telecaller", "Direction", "Call Status",
        "Duration (sec)", "Talk Time (sec)", "Disposition", "Notes", "Recording URL"
    ])

    for c in calls:
        lead_name = f"{c.lead.first_name} {c.lead.last_name or ''}".strip() if c.lead else "Customer"
        writer.writerow([
            c.id,
            c.started_at.strftime("%Y-%m-%d %H:%M:%S") if c.started_at else "",
            lead_name,
            c.callee_number,
            c.lead.city if c.lead else "",
            c.lead.source if c.lead else "",
            c.telecaller.full_name if c.telecaller else "",
            c.direction,
            c.status,
            c.duration_seconds,
            c.talk_time_seconds,
            c.disposition.label if c.disposition else "Pending",
            c.notes or "",
            c.recording_url or ""
        ])

    output.seek(0)
    filename = f"call_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )

@router.get("/calls/export/excel")
def export_calls_excel(
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    agent_id: Optional[str] = None,
    status: Optional[str] = None,
    disposition_id: Optional[str] = None,
    source: Optional[str] = None,
    company_id: str = Depends(get_tenant_company_id),
    current_user: User = Depends(require_roles("admin", "manager")),
    db: Session = Depends(get_db)
):
    query = build_call_report_query(db, company_id, start_date, end_date, agent_id, status, disposition_id, source)
    calls = query.limit(5000).all()

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Call Logs Report"

    # Header styling
    header_fill = PatternFill(start_color="1E3A8A", end_color="1E3A8A", fill_type="solid") # Dark Blue
    header_font = Font(name="Calibri", size=11, bold=True, color="FFFFFF")
    align_center = Alignment(horizontal="center", vertical="center")

    headers = [
        "Date & Time", "Customer Name", "Customer Phone", "City",
        "Lead Source", "Telecaller", "Status", "Duration (sec)",
        "Talk Time (sec)", "Disposition", "Notes", "Recording URL"
    ]
    ws.append(headers)

    for col_num in range(1, len(headers) + 1):
        cell = ws.cell(row=1, column=col_num)
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = align_center

    for c in calls:
        lead_name = f"{c.lead.first_name} {c.lead.last_name or ''}".strip() if c.lead else "Customer"
        ws.append([
            c.started_at.strftime("%Y-%m-%d %H:%M:%S") if c.started_at else "",
            lead_name,
            c.callee_number,
            c.lead.city if c.lead else "",
            c.lead.source if c.lead else "",
            c.telecaller.full_name if c.telecaller else "",
            c.status.upper(),
            c.duration_seconds,
            c.talk_time_seconds,
            c.disposition.label if c.disposition else "Pending",
            c.notes or "",
            c.recording_url or ""
        ])

    # Auto-adjust column widths
    for col in ws.columns:
        max_len = 0
        col_letter = openpyxl.utils.get_column_letter(col[0].column)
        for cell in col:
            val_str = str(cell.value or "")
            if len(val_str) > max_len:
                max_len = len(val_str)
        ws.column_dimensions[col_letter].width = min(max(max_len + 3, 12), 40)

    stream = io.BytesIO()
    wb.save(stream)
    stream.seek(0)

    filename = f"call_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
    return StreamingResponse(
        stream,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )
