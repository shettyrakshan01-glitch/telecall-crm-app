---
title: TeleCall CRM
emoji: 📞
colorFrom: blue
colorTo: indigo
sdk: docker
app_port: 7860
pinned: false
---

# Telecalling CRM & Employee Tracking SaaS (Multi-Tenant)

A specialized multi-tenant SaaS CRM built **exclusively for telecalling, voice telephony, and employee productivity tracking**.

> 🚫 **Zero-Messaging Policy**: In strict accordance with the product specifications, this platform contains **no SMS, no WhatsApp, no email, and no bulk messaging** components anywhere.

---

## 🏗️ Architecture & Technology Stack

- **Backend**: Python 3.12 + FastAPI (High-performance async REST API, auto-generating OpenAPI docs at `/docs`)
- **Database**: PostgreSQL (Relational schema with multi-tenant `company_id` isolation, composite indexes for lakhs of leads, and local SQLite development fallback)
- **Security & RBAC**: JWT Authentication with role-based access control (`super_admin`, `admin`, `manager`, `telecaller`), bcrypt password hashing, and session audit history
- **Telephony Abstraction Layer**: Pluggable provider architecture supporting **Exotel**, **Ozonetel**, **Knowlarity**, **MyOperator**, and **Twilio**, with a built-in mock provider for immediate testing
- **Frontend**: Clean, responsive SaaS dashboard (Tailwind CSS, Lucide icons, glassmorphic UI, responsive audio recording player, and modal workflows)

---

## 📦 Implemented Modules (Phase 1)

### 1. Multi-Tenant Architecture & Super Admin Control
- Tenant isolation: every tenant query is scoped by `company_id`.
- **Super Admin Portal** (`/superadmin`):
  - Subscription Plans management with tier limits (`max_employees`, `max_leads`, `recording_retention_days`, module toggles).
  - Client company onboarding (creates company, subdomain, default admin, initial telephony config, and default stages).
  - Company suspension / activation toggles.

### 2. Login, Access & Session Auditing
- Dual login portal (`/login`):
  - Company Portal (matches tenant subdomain and user email).
  - Super Admin SaaS Portal.
- Complete login history tracking (IP address, User-Agent, location, login/logout timestamps, and session durations).
- Live telecaller shift tracking and break logging (`shift_date`, `clock_in_at`, `total_talk_time_sec`, `break_reason`).

### 3. Lead Management & Duplicate Detection
- Instant duplicate phone detection across the tenant company (`409 Conflict` prevention).
- Live duplicate check badge as the admin types the phone number.
- Customizable lead stages per company (`New`, `Interested`, `Callback`, `Not Interested`, `Converted`).
- Full lead timeline profile on one screen (`/api/v1/leads/{lead_id}`):
  - Customer demographics.
  - Complete call history with embedded playable recording audio player.
  - Historical assignment and transfer audit trail.
  - Next follow-up schedule and notes.
- **CSV & Excel (.xlsx) Import**:
  - Flexible column mapping (Name, Phone, City, Email).
  - Error and duplicate detection report (batch duplicate check, database duplicate skipping, row-level error reporting).

### 4. Lead Allocation & Transfer Engine
- **Bulk Lead Allocation**:
  - **Equal Split**: Evenly distributes selected leads across active telecallers.
  - **Custom Count Split**: Allocates custom counts per employee.
- **Lead Transfers with Mandatory Reason**:
  - Transfer single or multiple leads from one telecaller to another.
  - Requires a mandatory `transfer_reason` field for complete compliance.
  - Old interaction history remains fully visible to the new assignee.
  - Complete audit log (`assigned_by`, `from_user`, `to_user`, `transfer_reason`, `allocated_at`).

### 5. Follow-up System & Reminders
- Schedule next follow-up date, time, and priority directly after each call.
- Filter views: **Today**, **Tomorrow**, and **Overdue**.
- Overdue alerts visible to company administrators for team-wide managerial oversight.
- Auto-generation of callback follow-up tasks when a call is missed or unanswered.

### 6. Calling Features & Mandatory Call Gate
- **Click-to-Call**: Directly from the lead profile or lead list table.
- **Floating Active Call Pad**: Realistic call connection and live ticking timer.
- 🛑 **Mandatory Post-Call Disposition Gate**:
  - The telecaller **cannot place another call** until disposition and notes are submitted for their previous call.
  - Submitting disposition clears the gate, logs shift talk time, moves the lead stage, and optionally schedules the next follow-up.
- **Call Recordings**: Stored with duration, start/end timestamps, call direction, and status.

---

## 🚀 Quick Start Guide

### 1. Prerequisites
- Python 3.12+ installed
- PostgreSQL (or use the built-in SQLite database for immediate zero-config testing)

### 2. Installation
```powershell
# Clone or navigate to the project directory
cd "CRM project"

# Activate the virtual environment
.\venv\Scripts\Activate.ps1

# Install dependencies (if not already installed)
pip install -r requirements.txt
```

### 3. Database Setup & Seeding
```powershell
# Run the seed script to create all tables and initial demo data
python backend/seed.py
```

### 4. Start the Application Server
```powershell
python run.py
```
The server will start on **`http://localhost:8000`**.

---

## 🔑 Seeded Demo Credentials

| Portal | URL | Email | Password | Subdomain | Role |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **Company Admin** | `http://localhost:8000/admin` | `admin@apex.com` | `Password@123` | `apex` | Company Owner / Admin |
| **Telecaller 1** | `http://localhost:8000/workspace` | `priya@apex.com` | `Password@123` | `apex` | Calling Agent |
| **Telecaller 2** | `http://localhost:8000/workspace` | `amit@apex.com` | `Password@123` | `apex` | Calling Agent |
| **Telecaller 3** | `http://localhost:8000/workspace` | `sneha@apex.com` | `Password@123` | `apex` | Calling Agent |
| **Super Admin** | `http://localhost:8000/superadmin` | `superadmin@telecall.io` | `Password@123` | *(None)* | SaaS Platform Owner |

*Quick login buttons are available directly on the login screen (`/login`) for 1-click credential autofill.*

---

## 🧪 Automated Test Suite

To run the integration tests:
```powershell
.\venv\Scripts\python -m pytest -v tests/test_phase1.py
```
**Test Coverage Includes:**
- `/health` strictly calling-only verification
- Admin & Telecaller authentication and token issuance
- Duplicate phone number conflict detection (`409 Conflict`)
- Bulk allocation (equal split) and lead transfer with mandatory reason
- Call gate blocking (verifying a second call is blocked until disposition is submitted)

---

## 🗺️ Build Roadmap

- [x] **Phase 1: Login, Lead Management, Lead Allocation, Follow-ups, Disposition & Notes**
- [ ] **Phase 2: Telephony Integration & Webhooks (Exotel/Twilio live integration), In-app Push Notifications**
- [ ] **Phase 3: Auto-Dialer (Progressive & Preview Modes), Real-Time Dashboard, Productivity & Excel/PDF Reports**
- [ ] **Phase 4: Call Quality, Speech-to-Text Transcription & Sentiment Analysis**
