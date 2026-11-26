from fastapi import APIRouter, Depends, HTTPException, status, Request, Response
from sqlalchemy.orm import Session
from datetime import datetime, timezone
from typing import List

from backend.app.config import settings
from backend.app.database import get_db
from backend.app.models.user import User, LoginHistory, TelecallerShift
from backend.app.models.company import Company, SuperAdminAudit
from backend.app.schemas.auth import LoginRequest, Token, UserProfileResponse, LoginHistoryResponse, PasswordResetRequest
from backend.app.security.auth import verify_password, get_password_hash, create_access_token
from backend.app.security.dependencies import get_current_user, require_roles

router = APIRouter(prefix="/auth", tags=["Authentication"])

@router.post("/login", response_model=Token)
def login(request: Request, response: Response, login_data: LoginRequest, db: Session = Depends(get_db)):
    # 1. Look up user by email
    query = db.query(User).filter(User.email == login_data.email.strip().lower())
    
    # If subdomain provided, match with company subdomain
    if login_data.subdomain:
        query = query.join(Company).filter(Company.subdomain == login_data.subdomain.strip().lower())

    user = query.first()

    if not user or not verify_password(login_data.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password."
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account is deactivated. Please contact your company administrator."
        )

    if user.role == "super_admin" and not settings.SUPER_ADMIN_ENABLED:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Super Admin login is currently disabled."
        )

    # If tenant user, verify company is active
    if user.company_id:
        company = db.query(Company).filter(Company.id == user.company_id).first()
        if not company or not company.is_active:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Your company account is inactive or subscription suspended."
            )

    # 2. Record Login History
    now = datetime.now(timezone.utc)
    client_ip = request.client.host if request.client else "127.0.0.1"
    user_agent = request.headers.get("user-agent", "Unknown Browser")[:250]
    
    login_entry = LoginHistory(
        company_id=user.company_id,
        user_id=user.id,
        ip_address=client_ip,
        user_agent=user_agent,
        location_city="Local Workstation",
        login_at=now
    )
    db.add(login_entry)

    # Update agent status to idle if they are a telecaller
    if user.role == "telecaller":
        user.agent_status = "idle"
        user.status_updated_at = now
        
        # Ensure today's shift record exists
        today_date = now.date()
        shift = db.query(TelecallerShift).filter(
            TelecallerShift.company_id == user.company_id,
            TelecallerShift.user_id == user.id,
            TelecallerShift.shift_date == today_date
        ).first()
        if not shift:
            shift = TelecallerShift(
                company_id=user.company_id,
                user_id=user.id,
                shift_date=today_date,
                clock_in_at=now
            )
            db.add(shift)

    db.commit()

    # 3. Issue JWT Token
    access_token = create_access_token(
        data={
            "sub": user.id,
            "email": user.email,
            "role": user.role,
            "company_id": user.company_id
        }
    )

    # Set cookie for direct browser access
    response.set_cookie(
        key="access_token",
        value=f"Bearer {access_token}",
        httponly=True,
        samesite="lax",
        max_age=60 * 60 * 12
    )

    return Token(
        access_token=access_token,
        token_type="bearer",
        user_id=user.id,
        email=user.email,
        full_name=user.full_name,
        role=user.role,
        company_id=user.company_id,
        company_name=user.company.name if user.company else "SaaS Platform"
    )

@router.post("/logout")
def logout(response: Response, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    now = datetime.now(timezone.utc)
    
    # Update latest login history record with logout_at
    latest_login = db.query(LoginHistory).filter(
        LoginHistory.user_id == current_user.id,
        LoginHistory.logout_at.is_(None)
    ).order_by(LoginHistory.login_at.desc()).first()

    if latest_login:
        latest_login.logout_at = now
        duration = int((now - latest_login.login_at.replace(tzinfo=timezone.utc)).total_seconds())
        latest_login.session_duration_seconds = max(0, duration)

    current_user.agent_status = "offline"
    current_user.status_updated_at = now
    db.commit()

    response.delete_cookie("access_token")
    return {"status": "success", "message": "Logged out successfully."}

@router.get("/me", response_model=UserProfileResponse)
def get_current_profile(current_user: User = Depends(get_current_user)):
    return UserProfileResponse(
        id=current_user.id,
        email=current_user.email,
        full_name=current_user.full_name,
        phone=current_user.phone,
        role=current_user.role,
        agent_status=current_user.agent_status,
        company_id=current_user.company_id,
        company_name=current_user.company.name if current_user.company else "Super Admin Platform",
        is_active=current_user.is_active,
        is_super_admin_session=getattr(current_user, "is_super_admin_session", False),
        super_admin_email=getattr(current_user, "super_admin_email", None)
    )

@router.get("/login-history", response_model=List[LoginHistoryResponse])
def get_user_login_history(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    query = db.query(LoginHistory).filter(LoginHistory.company_id == current_user.company_id)
    
    # If telecaller, only their own history; if admin, sees entire company's login audit
    if current_user.role == "telecaller":
        query = query.filter(LoginHistory.user_id == current_user.id)

    records = query.order_by(LoginHistory.login_at.desc()).limit(100).all()
    
    results = []
    for r in records:
        results.append(LoginHistoryResponse(
            id=r.id,
            user_id=r.user_id,
            user_name=r.user.full_name if r.user else "User",
            user_email=r.user.email if r.user else "",
            ip_address=r.ip_address,
            user_agent=r.user_agent,
            location_city=r.location_city,
            login_at=r.login_at,
            logout_at=r.logout_at,
            session_duration_seconds=r.session_duration_seconds
        ))
    return results

@router.get("/superadmin-oversight-info")
def get_superadmin_oversight_info(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Returns transparency status showing that SaaS Super Admin has active Master Access
    across all client tenant admin and agent workspaces.
    """
    if not settings.SUPER_ADMIN_ENABLED:
        return {
            "master_oversight_active": False,
            "superadmin_disabled": True,
            "recent_oversight_events": []
        }

    company_id = current_user.company_id
    super_admin_user = db.query(User).filter(User.role == "super_admin").first()

    recent_audits = []
    if company_id:
        audits = db.query(SuperAdminAudit).filter(
            SuperAdminAudit.target_company_id == company_id
        ).order_by(SuperAdminAudit.created_at.desc()).limit(10).all()

        for a in audits:
            recent_audits.append({
                "action_type": a.action_type,
                "description": a.description,
                "target_user_name": a.target_user_name,
                "target_role": a.target_role,
                "created_at": a.created_at.isoformat() if a.created_at else None
            })

    return {
        "master_oversight_active": True,
        "platform_owner_name": super_admin_user.full_name if super_admin_user else "CRM SaaS Platform Owner",
        "superadmin_email": super_admin_user.email if super_admin_user else "superadmin@telecall.io",
        "superadmin_role": "Platform Super Admin (Master Oversight)",
        "access_scope": "Full Supervisory & Audit Access over Company Admin and All Telecaller Agents",
        "transparency_notice": "Platform Super Admin maintains master supervisory privileges to oversee calling operations, agent compliance, data backups, and technical infrastructure.",
        "recent_oversight_events": recent_audits
    }

