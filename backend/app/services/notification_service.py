from datetime import datetime, timezone
from typing import List, Optional, Dict, Any
from sqlalchemy.orm import Session
from backend.app.models.notification import Notification
from backend.app.models.user import User

def create_notification(
    db: Session,
    company_id: str,
    user_id: str,
    type: str, # lead_assigned, followup_due, missed_call, admin_alert
    title: str,
    message: str,
    reference_id: Optional[str] = None
) -> Notification:
    """
    Creates an in-app notification record for a specific user.
    """
    notification = Notification(
        company_id=company_id,
        user_id=user_id,
        type=type,
        title=title,
        message=message,
        reference_id=reference_id,
        is_read=False,
        created_at=datetime.now(timezone.utc)
    )
    db.add(notification)
    db.commit()
    db.refresh(notification)
    return notification

def notify_lead_assigned(
    db: Session,
    company_id: str,
    telecaller_id: str,
    lead_name: str,
    lead_phone: str,
    lead_id: str
):
    create_notification(
        db=db,
        company_id=company_id,
        user_id=telecaller_id,
        type="lead_assigned",
        title="New Lead Assigned",
        message=f"You have been assigned lead: {lead_name} ({lead_phone}).",
        reference_id=lead_id
    )

def notify_missed_call(
    db: Session,
    company_id: str,
    telecaller_id: str,
    lead_name: str,
    lead_phone: str,
    lead_id: str
):
    create_notification(
        db=db,
        company_id=company_id,
        user_id=telecaller_id,
        type="missed_call",
        title="Missed Call / Callback Needed",
        message=f"Missed call / unanswered contact with {lead_name} ({lead_phone}). Callback task auto-scheduled.",
        reference_id=lead_id
    )

def notify_admin_overdue_followups(
    db: Session,
    company_id: str,
    overdue_count: int
):
    """
    Broadcasts an overdue follow-up alert to all company administrators.
    """
    admins = db.query(User).filter(
        User.company_id == company_id,
        User.role == "admin",
        User.is_active == True
    ).all()

    for admin in admins:
        create_notification(
            db=db,
            company_id=company_id,
            user_id=admin.id,
            type="admin_alert",
            title="Overdue Follow-ups Alert",
            message=f"There are {overdue_count} overdue follow-up tasks requiring managerial attention.",
            reference_id=None
        )

def get_user_notifications(
    db: Session,
    company_id: str,
    user_id: str,
    unread_only: bool = False,
    limit: int = 30
) -> List[Notification]:
    query = db.query(Notification).filter(
        Notification.company_id == company_id,
        Notification.user_id == user_id
    )
    if unread_only:
        query = query.filter(Notification.is_read == False)
    return query.order_by(Notification.created_at.desc()).limit(limit).all()

def mark_notification_read(db: Session, company_id: str, user_id: str, notification_id: str) -> bool:
    notif = db.query(Notification).filter(
        Notification.id == notification_id,
        Notification.company_id == company_id,
        Notification.user_id == user_id
    ).first()
    if notif:
        notif.is_read = True
        db.commit()
        return True
    return False

def mark_all_notifications_read(db: Session, company_id: str, user_id: str):
    db.query(Notification).filter(
        Notification.company_id == company_id,
        Notification.user_id == user_id,
        Notification.is_read == False
    ).update({"is_read": True})
    db.commit()
