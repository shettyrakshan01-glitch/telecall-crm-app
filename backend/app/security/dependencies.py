from fastapi import Depends, HTTPException, status, Request
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session
from typing import List, Optional
from datetime import datetime, timezone

from backend.app.config import settings
from backend.app.database import get_db
from backend.app.models.user import User, LoginHistory
from backend.app.models.company import Company
from backend.app.models.call import CallLog, CallDisposition
from backend.app.security.auth import decode_access_token

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login", auto_error=False)

def get_token_from_header_or_cookie(request: Request, token: Optional[str] = Depends(oauth2_scheme)) -> Optional[str]:
    if token:
        return token
    # Also support cookie-based auth for seamless browser navigation
    cookie_token = request.cookies.get("access_token")
    if cookie_token:
        if cookie_token.startswith("Bearer "):
            return cookie_token[7:]
        return cookie_token
    return None

def get_current_user(
    token: Optional[str] = Depends(get_token_from_header_or_cookie),
    db: Session = Depends(get_db)
) -> User:
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials or session has expired.",
        headers={"WWW-Authenticate": "Bearer"},
    )
    if not token:
        raise credentials_exception

    payload = decode_access_token(token)
    if payload is None:
        raise credentials_exception

    user_id: str = payload.get("sub")
    if user_id is None:
        raise credentials_exception

    user = db.query(User).filter(User.id == user_id).first()
    if user is None:
        raise credentials_exception
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User account is deactivated. Contact your administrator."
        )
    if user.role == "super_admin" and not settings.SUPER_ADMIN_ENABLED:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Super Admin access is currently disabled."
        )

    user.is_super_admin_session = payload.get("is_super_admin_session", False) if settings.SUPER_ADMIN_ENABLED else False
    user.super_admin_email = payload.get("super_admin_email", None) if settings.SUPER_ADMIN_ENABLED else None

    return user

def require_super_admin_enabled():
    if not settings.SUPER_ADMIN_ENABLED:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Super Admin module is currently disabled."
        )

def require_roles(*allowed_roles: str):
    def role_checker(current_user: User = Depends(get_current_user)) -> User:
        if current_user.role not in allowed_roles and current_user.role != "super_admin":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Access denied. Requires one of roles: {', '.join(allowed_roles)}"
            )
        return current_user
    return role_checker

def get_tenant_company_id(
    request: Request,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
) -> str:
    """
    Enforces multi-tenant isolation. Ensures company_id is present on all tenant endpoints.
    For Super Admin, dynamically resolves the active tenant via header (x-company-id),
    query parameter (company_id), user company_id, or defaults to the first active company!
    """
    if current_user.role == "super_admin":
        header_company = request.headers.get("x-company-id")
        if header_company:
            return header_company
        query_company = request.query_params.get("company_id")
        if query_company:
            return query_company
        if current_user.company_id:
            return current_user.company_id
        first_comp = db.query(Company).filter(Company.is_active == True).first()
        if first_comp:
            return first_comp.id
        return None

    if not current_user.company_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="User has no company association."
        )
    return current_user.company_id

def verify_call_gate_clear(user_id: str, company_id: str, db: Session):
    """
    Clears any abandoned previous calls by auto-disposing with default disposition
    so that telecallers can dial smoothly without getting stuck or blocked.
    """
    undisposed = db.query(CallLog).filter(
        CallLog.company_id == company_id,
        CallLog.telecaller_id == user_id,
        CallLog.disposition_id.is_(None)
    ).all()

    if undisposed:
        default_disp = db.query(CallDisposition).filter(
            CallDisposition.company_id == company_id,
            CallDisposition.is_active == True
        ).first()
        disp_id = default_disp.id if default_disp else None
        disp_label = default_disp.label if default_disp else "Call Disconnect"
        now = datetime.now(timezone.utc)
        for call in undisposed:
            call.disposition_id = disp_id
            call.notes = disp_label
            call.disposition_submitted_at = now
            if not call.ended_at:
                call.ended_at = now
            if call.status in ("initiated", "connected"):
                call.status = "completed"
        db.commit()
