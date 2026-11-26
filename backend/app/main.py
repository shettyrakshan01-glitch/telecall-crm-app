import os
from fastapi import FastAPI, Request, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, FileResponse, RedirectResponse, JSONResponse
from contextlib import asynccontextmanager

from backend.app.config import settings
from backend.app.security.auth import decode_access_token
from backend.app.database import engine, Base
from backend.app.security.dependencies import require_super_admin_enabled
from backend.app.api.auth_router import router as auth_router
from backend.app.api.superadmin_router import router as superadmin_router
from backend.app.api.employee_router import router as employee_router
from backend.app.api.lead_router import router as lead_router
from backend.app.api.allocation_router import router as allocation_router
from backend.app.api.followup_router import router as followup_router
from backend.app.api.call_router import router as call_router
from backend.app.api.telephony_router import router as telephony_router
from backend.app.api.notification_router import router as notification_router
from backend.app.api.autodialer_router import router as autodialer_router
from backend.app.api.dashboard_router import router as dashboard_router
from backend.app.api.report_router import router as report_router

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Ensure database schema is created on startup
    Base.metadata.create_all(bind=engine)
    yield

app = FastAPI(
    title=settings.PROJECT_NAME,
    version=settings.VERSION,
    description="Multi-Tenant Telecalling CRM & Employee Tracking SaaS Backend (Strictly Calling & Tracking)",
    lifespan=lifespan
)

# CORS setup
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.middleware("http")
async def add_no_cache_headers(request: Request, call_next):
    response = await call_next(request)
    path = request.url.path
    if path in ("/", "/login", "/admin", "/workspace", "/superadmin"):
        response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"
    elif path.startswith("/static/"):
        if "v" in request.query_params or path.endswith(("lucide.min.js", "chart.min.js")):
            response.headers["Cache-Control"] = "public, max-age=604800"
        else:
            response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    return response

# API Routers
app.include_router(auth_router, prefix=settings.API_PREFIX)
app.include_router(
    superadmin_router,
    prefix=settings.API_PREFIX,
    dependencies=[Depends(require_super_admin_enabled)]
)
app.include_router(employee_router, prefix=settings.API_PREFIX)
app.include_router(lead_router, prefix=settings.API_PREFIX)
app.include_router(allocation_router, prefix=settings.API_PREFIX)
app.include_router(followup_router, prefix=settings.API_PREFIX)
app.include_router(call_router, prefix=settings.API_PREFIX)
app.include_router(telephony_router, prefix=settings.API_PREFIX)
app.include_router(notification_router, prefix=settings.API_PREFIX)
app.include_router(autodialer_router, prefix=settings.API_PREFIX)
app.include_router(dashboard_router, prefix=settings.API_PREFIX)
app.include_router(report_router, prefix=settings.API_PREFIX)

# Static & Frontend paths
BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
FRONTEND_DIR = os.path.join(BASE_DIR, "frontend")
STATIC_DIR = os.path.join(FRONTEND_DIR, "static")
TEMPLATES_DIR = os.path.join(FRONTEND_DIR, "templates")

if os.path.exists(STATIC_DIR):
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

if os.path.exists(settings.UPLOAD_DIR):
    app.mount("/uploads", StaticFiles(directory=settings.UPLOAD_DIR), name="uploads")

@app.get("/health")
def health_check():
    return {
        "status": "healthy",
        "service": settings.PROJECT_NAME,
        "version": settings.VERSION,
        "strictly_calling_only": True
    }

@app.get("/.well-known/assetlinks.json")
def serve_assetlinks():
    assetlinks_path = os.path.join(STATIC_DIR, "assetlinks.json")
    if os.path.exists(assetlinks_path):
        return FileResponse(assetlinks_path, media_type="application/json")
    return JSONResponse(content=[{
        "relation": ["delegate_permission/common.handle_all_urls"],
        "target": {
            "namespace": "android_app",
            "package_name": "com.onrender.telecall_crm.twa",
            "sha256_cert_fingerprints": [
                "11:7D:CD:B0:2A:3D:BA:D6:A7:27:AE:7D:AC:52:0A:13:88:5B:DC:86:2B:DC:8A:15:F9:46:F0:31:5E:A3:E4:0F"
            ],
        },
    }])

@app.get("/download-app")
def download_android_apk():
    apk_path = os.path.join(STATIC_DIR, "TeleCall_CRM.apk")
    if os.path.exists(apk_path):
        return FileResponse(
            apk_path,
            media_type='application/vnd.android.package-archive',
            filename="TeleCall_CRM.apk"
        )
    return RedirectResponse(
        url="https://github.com/shettyrakshan01-glitch/telecall-crm/releases/download/v1.0/_TeleCallCRM_20422996.apk"
    )

@app.get("/")
def serve_root(request: Request):
    # Auto-redirect logged-in users directly to their workspace to prevent accidental login screens
    token = request.cookies.get("access_token")
    if token:
        if token.startswith("Bearer "):
            token = token[7:]
        payload = decode_access_token(token)
        if payload and payload.get("sub"):
            role = payload.get("role")
            if role in ("admin", "manager"):
                return RedirectResponse(url="/admin", status_code=302)
            elif role == "telecaller":
                return RedirectResponse(url="/workspace", status_code=302)
            elif role == "super_admin":
                return RedirectResponse(url="/superadmin", status_code=302)
    return FileResponse(os.path.join(TEMPLATES_DIR, "login.html"))

@app.get("/login")
def serve_login(request: Request):
    token = request.cookies.get("access_token")
    if token:
        if token.startswith("Bearer "):
            token = token[7:]
        payload = decode_access_token(token)
        if payload and payload.get("sub"):
            role = payload.get("role")
            if role in ("admin", "manager"):
                return RedirectResponse(url="/admin", status_code=302)
            elif role == "telecaller":
                return RedirectResponse(url="/workspace", status_code=302)
            elif role == "super_admin":
                return RedirectResponse(url="/superadmin", status_code=302)
    return FileResponse(os.path.join(TEMPLATES_DIR, "login.html"))

@app.get("/admin", response_class=FileResponse)
def serve_admin():
    return FileResponse(os.path.join(TEMPLATES_DIR, "admin_dashboard.html"))

@app.get("/workspace", response_class=FileResponse)
def serve_employee_workspace():
    return FileResponse(os.path.join(TEMPLATES_DIR, "employee_workspace.html"))

@app.get("/superadmin")
def serve_superadmin():
    if not settings.SUPER_ADMIN_ENABLED:
        return RedirectResponse(url="/login")
    return FileResponse(os.path.join(TEMPLATES_DIR, "super_admin.html"))
