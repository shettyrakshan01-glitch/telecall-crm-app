from typing import List, Dict, Optional, Any
from datetime import datetime, timezone
from sqlalchemy.orm import Session
from fastapi import HTTPException, status

from backend.app.models.lead import Lead, LeadAllocation
from backend.app.models.user import User
from backend.app.services.notification_service import notify_lead_assigned

def assign_single_lead(
    db: Session,
    company_id: str,
    lead_id: str,
    to_user_id: str,
    assigned_by_id: str,
    reason: Optional[str] = "Manual Assignment"
) -> Lead:
    lead = db.query(Lead).filter(
        Lead.id == lead_id,
        Lead.company_id == company_id,
        Lead.is_deleted == False
    ).first()
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found.")

    target_user = db.query(User).filter(
        User.id == to_user_id,
        User.company_id == company_id,
        User.is_active == True
    ).first()
    if not target_user:
        raise HTTPException(status_code=404, detail="Target employee not found or inactive.")

    from_user_id = lead.assigned_to

    lead.assigned_to = to_user_id
    lead.assigned_at = datetime.now(timezone.utc)

    # Record historical audit
    alloc_record = LeadAllocation(
        company_id=company_id,
        lead_id=lead.id,
        assigned_by=assigned_by_id,
        from_user_id=from_user_id,
        to_user_id=to_user_id,
        transfer_reason=reason
    )
    db.add(alloc_record)
    
    # Notify target employee
    lead_name = f"{lead.first_name} {lead.last_name or ''}".strip()
    notify_lead_assigned(db, company_id, to_user_id, lead_name, lead.phone, lead.id)

    db.commit()
    db.refresh(lead)
    return lead

def bulk_allocate_leads(
    db: Session,
    company_id: str,
    lead_ids: List[str],
    employee_ids: List[str],
    assigned_by_id: str,
    mode: str = "equal", # "equal" or "custom"
    custom_counts: Optional[Dict[str, int]] = None
) -> Dict[str, Any]:
    if not lead_ids or not employee_ids:
        raise HTTPException(status_code=400, detail="Must provide at least one lead and one employee.")

    # Validate active employees
    employees = db.query(User).filter(
        User.id.in_(employee_ids),
        User.company_id == company_id,
        User.is_active == True
    ).all()
    if len(employees) != len(employee_ids):
        raise HTTPException(status_code=400, detail="One or more target employees are invalid or inactive.")

    leads = db.query(Lead).filter(
        Lead.id.in_(lead_ids),
        Lead.company_id == company_id,
        Lead.is_deleted == False
    ).all()

    if not leads:
        raise HTTPException(status_code=404, detail="No matching leads found to assign.")

    assignments = [] # (lead, target_emp_id)

    if mode == "equal":
        # Round-robin or even distribution
        emp_count = len(employee_ids)
        for i, lead in enumerate(leads):
            target_emp_id = employee_ids[i % emp_count]
            assignments.append((lead, target_emp_id))
    elif mode == "custom":
        if not custom_counts:
            raise HTTPException(status_code=400, detail="Custom counts map required for custom split mode.")
        lead_idx = 0
        total_leads = len(leads)
        for emp_id, count in custom_counts.items():
            if emp_id not in employee_ids:
                continue
            for _ in range(count):
                if lead_idx < total_leads:
                    assignments.append((leads[lead_idx], emp_id))
                    lead_idx += 1
        # If any leads remaining, distribute to first employee
        while lead_idx < total_leads:
            assignments.append((leads[lead_idx], employee_ids[0]))
            lead_idx += 1
    else:
        raise HTTPException(status_code=400, detail="Invalid allocation mode. Choose 'equal' or 'custom'.")

    now = datetime.now(timezone.utc)
    updated_count = 0

    for lead, target_emp_id in assignments:
        from_user_id = lead.assigned_to
        if from_user_id == target_emp_id:
            continue # already assigned to this person

        lead.assigned_to = target_emp_id
        lead.assigned_at = now

        alloc = LeadAllocation(
            company_id=company_id,
            lead_id=lead.id,
            assigned_by=assigned_by_id,
            from_user_id=from_user_id,
            to_user_id=target_emp_id,
            transfer_reason=f"Bulk Allocation ({mode} split)"
        )
        db.add(alloc)
        updated_count += 1

        lead_name = f"{lead.first_name} {lead.last_name or ''}".strip()
        notify_lead_assigned(db, company_id, target_emp_id, lead_name, lead.phone, lead.id)

    db.commit()
    return {
        "status": "success",
        "total_requested": len(lead_ids),
        "total_allocated": updated_count,
        "mode": mode
    }

def transfer_leads_with_reason(
    db: Session,
    company_id: str,
    lead_ids: List[str],
    to_employee_id: str,
    transfer_reason: str,
    assigned_by_id: str
) -> Dict[str, Any]:
    if not transfer_reason or not transfer_reason.strip():
        raise HTTPException(status_code=400, detail="Transfer reason is strictly required.")

    target_emp = db.query(User).filter(
        User.id == to_employee_id,
        User.company_id == company_id,
        User.is_active == True
    ).first()
    if not target_emp:
        raise HTTPException(status_code=404, detail="Target employee not found or inactive.")

    leads = db.query(Lead).filter(
        Lead.id.in_(lead_ids),
        Lead.company_id == company_id,
        Lead.is_deleted == False
    ).all()

    now = datetime.now(timezone.utc)
    transferred_count = 0

    for lead in leads:
        from_id = lead.assigned_to
        lead.assigned_to = to_employee_id
        lead.assigned_at = now

        alloc = LeadAllocation(
            company_id=company_id,
            lead_id=lead.id,
            assigned_by=assigned_by_id,
            from_user_id=from_id,
            to_user_id=to_employee_id,
            transfer_reason=transfer_reason.strip()
        )
        db.add(alloc)
        transferred_count += 1

        lead_name = f"{lead.first_name} {lead.last_name or ''}".strip()
        notify_lead_assigned(db, company_id, to_employee_id, lead_name, lead.phone, lead.id)

    db.commit()
    return {
        "status": "success",
        "transferred_count": transferred_count,
        "to_employee_name": target_emp.full_name,
        "transfer_reason": transfer_reason.strip()
    }
