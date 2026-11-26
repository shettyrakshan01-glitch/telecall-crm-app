from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List, Dict, Any

from backend.app.database import get_db
from backend.app.models.user import User
from backend.app.models.lead import LeadAllocation
from backend.app.schemas.lead import BulkAssignRequest, TransferLeadsRequest, SingleAssignRequest
from backend.app.services.allocation_service import (
    assign_single_lead, bulk_allocate_leads, transfer_leads_with_reason
)
from backend.app.security.dependencies import require_roles, get_tenant_company_id

router = APIRouter(prefix="/allocations", tags=["Lead Allocations & Transfers"])

@router.post("/single/{lead_id}")
def assign_single(
    lead_id: str,
    req: SingleAssignRequest,
    company_id: str = Depends(get_tenant_company_id),
    current_user: User = Depends(require_roles("admin", "manager")),
    db: Session = Depends(get_db)
):
    lead = assign_single_lead(
        db=db,
        company_id=company_id,
        lead_id=lead_id,
        to_user_id=req.employee_id,
        assigned_by_id=current_user.id,
        reason="Manual Assignment"
    )
    return {
        "status": "success",
        "lead_id": lead.id,
        "assigned_to": lead.assigned_to,
        "assigned_at": lead.assigned_at
    }

@router.post("/bulk")
def bulk_assign(
    req: BulkAssignRequest,
    company_id: str = Depends(get_tenant_company_id),
    current_user: User = Depends(require_roles("admin", "manager")),
    db: Session = Depends(get_db)
):
    return bulk_allocate_leads(
        db=db,
        company_id=company_id,
        lead_ids=req.lead_ids,
        employee_ids=req.employee_ids,
        assigned_by_id=current_user.id,
        mode=req.mode,
        custom_counts=req.custom_counts
    )

@router.post("/transfer")
def transfer_leads(
    req: TransferLeadsRequest,
    company_id: str = Depends(get_tenant_company_id),
    current_user: User = Depends(require_roles("admin", "manager")),
    db: Session = Depends(get_db)
):
    return transfer_leads_with_reason(
        db=db,
        company_id=company_id,
        lead_ids=req.lead_ids,
        to_employee_id=req.to_employee_id,
        transfer_reason=req.transfer_reason,
        assigned_by_id=current_user.id
    )

@router.get("/history/{lead_id}")
def get_lead_allocation_history(
    lead_id: str,
    company_id: str = Depends(get_tenant_company_id),
    current_user: User = Depends(require_roles("admin", "manager", "telecaller")),
    db: Session = Depends(get_db)
):
    allocs = db.query(LeadAllocation).filter(
        LeadAllocation.lead_id == lead_id,
        LeadAllocation.company_id == company_id
    ).order_by(LeadAllocation.allocated_at.desc()).all()

    results = []
    for a in allocs:
        results.append({
            "id": a.id,
            "assigned_by_name": a.assigner.full_name if a.assigner else "System",
            "from_user_name": a.from_user.full_name if a.from_user else "Unassigned",
            "to_user_name": a.to_user.full_name if a.to_user else "Unassigned",
            "transfer_reason": a.transfer_reason,
            "allocated_at": a.allocated_at
        })
    return results
