from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from typing import List, Dict, Any
from datetime import datetime, timezone

from backend.app.database import get_db
from backend.app.models.user import User
from backend.app.models.notification import Notification
from backend.app.models.followup import FollowUp
from backend.app.services.notification_service import (
    get_user_notifications, mark_notification_read,
    mark_all_notifications_read, notify_admin_overdue_followups
)
from backend.app.security.dependencies import get_current_user, get_tenant_company_id

router = APIRouter(prefix="/notifications", tags=["In-App Notifications"])

@router.get("", response_model=List[Dict[str, Any]])
def list_notifications(
    unread_only: bool = False,
    limit: int = Query(30, ge=1, le=100),
    company_id: str = Depends(get_tenant_company_id),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    notifs = get_user_notifications(db, company_id, current_user.id, unread_only, limit)
    results = []
    for n in notifs:
        results.append({
            "id": n.id,
            "type": n.type,
            "title": n.title,
            "message": n.message,
            "reference_id": n.reference_id,
            "is_read": n.is_read,
            "created_at": n.created_at
        })
    return results

@router.get("/unread-count")
def get_unread_count(
    company_id: str = Depends(get_tenant_company_id),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    count = db.query(Notification).filter(
        Notification.company_id == company_id,
        Notification.user_id == current_user.id,
        Notification.is_read == False
    ).count()
    return {"unread_count": count}

@router.put("/{notification_id}/read")
def mark_as_read(
    notification_id: str,
    company_id: str = Depends(get_tenant_company_id),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    success = mark_notification_read(db, company_id, current_user.id, notification_id)
    if not success:
        raise HTTPException(status_code=404, detail="Notification not found.")
    return {"status": "success"}

@router.post("/read-all")
def mark_all_read(
    company_id: str = Depends(get_tenant_company_id),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    mark_all_notifications_read(db, company_id, current_user.id)
    return {"status": "success"}

@router.post("/check-admin-alerts")
def check_admin_alerts(
    company_id: str = Depends(get_tenant_company_id),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Checks for overdue follow-ups across the company and alerts admin if needed.
    """
    if current_user.role not in ("admin", "manager"):
        return {"status": "skipped", "reason": "Only managers/admins receive overdue alerts"}

    now = datetime.now(timezone.utc)
    overdue_count = db.query(FollowUp).filter(
        FollowUp.company_id == company_id,
        FollowUp.scheduled_at < now,
        FollowUp.status == "pending"
    ).count()

    if overdue_count > 0:
        # Check if alert already sent in the last hour
        existing = db.query(Notification).filter(
            Notification.company_id == company_id,
            Notification.user_id == current_user.id,
            Notification.type == "admin_alert",
            Notification.created_at >= now.replace(minute=0, second=0)
        ).first()

        if not existing:
            notify_admin_overdue_followups(db, company_id, overdue_count)

    return {"status": "success", "overdue_count": overdue_count}
