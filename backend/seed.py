import sys
import os
from datetime import datetime, timezone, timedelta, date

# Add project root to sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from backend.app.database import engine, SessionLocal, Base
from backend.app.models import (
    SubscriptionPlan, Company, TelephonyConfig, User,
    LeadStage, Lead, LeadAllocation, CallDisposition, CallLog, FollowUp
)
from backend.app.security.auth import get_password_hash

def seed_database():
    print("Creating all database tables...")
    Base.metadata.create_all(bind=engine)

    db = SessionLocal()
    try:
        # Check if already seeded
        existing_super = db.query(User).filter(User.role == "super_admin").first()
        if existing_super:
            print("Database already contains data. Skipping re-seed.")
            return

        print("Seeding Subscription Plans...")
        starter_plan = SubscriptionPlan(
            name="Starter Plan",
            tier="starter",
            max_employees=5,
            max_leads=10000,
            recording_retention_days=30,
            has_auto_dialer=False,
            has_sentiment_analysis=False
        )
        growth_plan = SubscriptionPlan(
            name="Growth Plan",
            tier="growth",
            max_employees=25,
            max_leads=100000,
            recording_retention_days=90,
            has_auto_dialer=True,
            has_sentiment_analysis=False
        )
        enterprise_plan = SubscriptionPlan(
            name="Enterprise Plan",
            tier="enterprise",
            max_employees=100,
            max_leads=1000000,
            recording_retention_days=365,
            has_auto_dialer=True,
            has_sentiment_analysis=True
        )
        db.add_all([starter_plan, growth_plan, enterprise_plan])
        db.flush()

        print("Seeding Super Admin user...")
        super_admin = User(
            company_id=None,
            email="superadmin@telecall.io",
            password_hash=get_password_hash("Password@123"),
            full_name="CRM SaaS Super Admin",
            phone="+919999999999",
            role="super_admin",
            agent_status="offline"
        )
        db.add(super_admin)
        db.flush()

        print("Seeding Demo Tenant: Apex Realty Global...")
        apex_company = Company(
            name="Apex Realty Global",
            subdomain="apex",
            plan_id=growth_plan.id,
            is_active=True
        )
        db.add(apex_company)
        db.flush()

        # Telephony Config for Apex
        apex_telephony = TelephonyConfig(
            company_id=apex_company.id,
            provider="mock",
            api_key="mock_key_apex",
            api_token="mock_token_apex",
            virtual_number="+918000554433",
            recording_consent_enabled=True,
            consent_announcement_text="This call is recorded for quality assurance.",
            retention_days=90
        )
        db.add(apex_telephony)

        # Company Admin
        apex_admin = User(
            company_id=apex_company.id,
            email="admin@apex.com",
            password_hash=get_password_hash("Password@123"),
            full_name="Rajesh Sharma (Admin)",
            phone="+919876543210",
            role="admin",
            agent_status="offline"
        )
        db.add(apex_admin)
        db.flush()

        # Telecallers
        telecaller1 = User(
            company_id=apex_company.id,
            email="priya@apex.com",
            password_hash=get_password_hash("Password@123"),
            full_name="Priya Patel",
            phone="+919876543211",
            role="telecaller",
            agent_status="idle"
        )
        telecaller2 = User(
            company_id=apex_company.id,
            email="amit@apex.com",
            password_hash=get_password_hash("Password@123"),
            full_name="Amit Verma",
            phone="+919876543212",
            role="telecaller",
            agent_status="idle"
        )
        telecaller3 = User(
            company_id=apex_company.id,
            email="sneha@apex.com",
            password_hash=get_password_hash("Password@123"),
            full_name="Sneha Roy",
            phone="+919876543213",
            role="telecaller",
            agent_status="idle"
        )
        db.add_all([telecaller1, telecaller2, telecaller3])
        db.flush()

        # Lead Stages
        stages = [
            ("New", "#3B82F6", 0, False),
            ("Interested", "#10B981", 1, False),
            ("Callback", "#F59E0B", 2, False),
            ("Not Interested", "#EF4444", 3, False),
            ("Converted", "#8B5CF6", 4, True)
        ]
        stage_objs = {}
        for s_name, s_color, s_order, is_t in stages:
            stg = LeadStage(
                company_id=apex_company.id,
                name=s_name,
                color_hex=s_color,
                order_index=s_order,
                is_terminal=is_t,
                is_system=True
            )
            db.add(stg)
            db.flush()
            stage_objs[s_name] = stg

        # Call Dispositions
        disps = [
            ("CALL_DISCONNECT", "Call Disconnect", False),
            ("BUSY", "Busy", True),
            ("RINGING", "Ringing", True),
            ("CALL_BACK", "Call Back", True),
            ("NOT_INTERESTED", "Not Interested", False),
            ("OTHER", "Other", False)
        ]
        disp_objs = {}
        for code, label, req_fup in disps:
            cd = CallDisposition(
                company_id=apex_company.id,
                code=code,
                label=label,
                requires_followup=req_fup
            )
            db.add(cd)
            db.flush()
            disp_objs[code] = cd

        print("Seeding Sample Leads and Call Records...")
        sample_leads_data = [
            ("Vikram", "Malhotra", "+919811122233", "vikram@example.com", "Mumbai", "Website Inquiry", stage_objs["Interested"], telecaller1),
            ("Ananya", "Deshmukh", "+919822233344", "ananya@example.com", "Pune", "Housing Expo", stage_objs["Callback"], telecaller1),
            ("Rohan", "Kapoor", "+919833344455", "rohan@example.com", "Delhi NCR", "CSV Import", stage_objs["New"], telecaller2),
            ("Deepa", "Iyer", "+919844455566", "deepa@example.com", "Bengaluru", "Property Portal", stage_objs["New"], telecaller2),
            ("Kavita", "Joshi", "+919855566677", "kavita@example.com", "Ahmedabad", "Website Inquiry", stage_objs["Converted"], telecaller3),
            ("Suresh", "Nair", "+919866677788", "suresh@example.com", "Kochi", "Referral", stage_objs["New"], None), # Unassigned
            ("Meera", "Sen", "+919877788899", "meera@example.com", "Kolkata", "CSV Import", stage_objs["New"], None), # Unassigned
        ]

        now = datetime.now(timezone.utc)

        for fname, lname, phone, email, city, src, stage, assignee in sample_leads_data:
            lead = Lead(
                company_id=apex_company.id,
                first_name=fname,
                last_name=lname,
                phone=phone,
                email=email,
                city=city,
                source=src,
                stage_id=stage.id,
                assigned_to=assignee.id if assignee else None,
                assigned_at=now if assignee else None,
                tags=["High Intent"] if stage.name in ("Interested", "Converted") else ["Standard"]
            )
            db.add(lead)
            db.flush()

            if assignee:
                alloc = LeadAllocation(
                    company_id=apex_company.id,
                    lead_id=lead.id,
                    assigned_by=apex_admin.id,
                    from_user_id=None,
                    to_user_id=assignee.id,
                    transfer_reason="Initial Campaign Allocation"
                )
                db.add(alloc)

            # Add completed sample call for Vikram
            if fname == "Vikram":
                call = CallLog(
                    company_id=apex_company.id,
                    lead_id=lead.id,
                    telecaller_id=telecaller1.id,
                    direction="outbound",
                    provider_call_sid="mock-sid-001",
                    caller_number=telecaller1.phone,
                    callee_number=lead.phone,
                    status="completed",
                    started_at=now - timedelta(hours=2),
                    answered_at=now - timedelta(hours=2) + timedelta(seconds=8),
                    ended_at=now - timedelta(hours=2) + timedelta(seconds=145),
                    duration_seconds=145,
                    talk_time_seconds=137,
                    recording_url="https://actions.google.com/sounds/v1/telephones/telephone_ring_analog.ogg",
                    disposition_id=disp_objs["CALL_BACK"].id,
                    disposition_submitted_at=now - timedelta(hours=2) + timedelta(seconds=160),
                    notes="Client interested in 3BHK high-rise apartment. Scheduled site visit for tomorrow afternoon."
                )
                db.add(call)
                lead.total_calls_count = 1
                lead.last_call_at = call.started_at

                # Follow-up for Vikram (Tomorrow)
                fup = FollowUp(
                    company_id=apex_company.id,
                    lead_id=lead.id,
                    call_log_id=call.id,
                    assigned_to=telecaller1.id,
                    created_by=telecaller1.id,
                    scheduled_at=now + timedelta(days=1),
                    priority="high",
                    notes="Site visit demo & brochure delivery."
                )
                db.add(fup)
                lead.next_followup_at = fup.scheduled_at

            # Add overdue follow-up for Ananya
            if fname == "Ananya":
                fup_overdue = FollowUp(
                    company_id=apex_company.id,
                    lead_id=lead.id,
                    assigned_to=telecaller1.id,
                    created_by=telecaller1.id,
                    scheduled_at=now - timedelta(hours=4), # Overdue!
                    priority="normal",
                    notes="Follow-up call on loan pre-approval."
                )
                db.add(fup_overdue)
                lead.next_followup_at = fup_overdue.scheduled_at

        db.commit()
        print("Database seeded successfully!")

    finally:
        db.close()

if __name__ == "__main__":
    seed_database()
