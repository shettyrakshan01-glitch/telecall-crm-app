import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))
import sqlite3
from backend.app.database import engine, Base
from backend.app.models import *

def migrate():
    con = sqlite3.connect('crm.db')
    cur = con.cursor()
    
    # Check leads columns
    cur.execute("PRAGMA table_info(leads)")
    cols = [c[1] for c in cur.fetchall()]
    if 'import_batch_id' not in cols:
        print("Adding import_batch_id to leads table...")
        cur.execute("ALTER TABLE leads ADD COLUMN import_batch_id VARCHAR(36)")

    # Check telephony_configs columns
    cur.execute("PRAGMA table_info(telephony_configs)")
    tele_cols = [c[1] for c in cur.fetchall()]
    if 'allow_manual_dialing' not in tele_cols:
        print("Adding allow_manual_dialing to telephony_configs...")
        cur.execute("ALTER TABLE telephony_configs ADD COLUMN allow_manual_dialing BOOLEAN DEFAULT 1")
    if 'working_hours_start' not in tele_cols:
        print("Adding working_hours_start to telephony_configs...")
        cur.execute("ALTER TABLE telephony_configs ADD COLUMN working_hours_start VARCHAR(10) DEFAULT '09:00'")
    if 'working_hours_end' not in tele_cols:
        print("Adding working_hours_end to telephony_configs...")
        cur.execute("ALTER TABLE telephony_configs ADD COLUMN working_hours_end VARCHAR(10) DEFAULT '19:00'")
    if 'allow_agent_bulk_upload' not in tele_cols:
        print("Adding allow_agent_bulk_upload to telephony_configs...")
        cur.execute("ALTER TABLE telephony_configs ADD COLUMN allow_agent_bulk_upload BOOLEAN DEFAULT 0")

    con.commit()
    con.close()

    # Create new tables such as lead_import_history
    Base.metadata.create_all(bind=engine)
    print("Database migration completed successfully!")

if __name__ == "__main__":
    migrate()
