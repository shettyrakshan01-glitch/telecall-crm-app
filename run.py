import uvicorn
import os
import sys

# Ensure project root is in python path
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

if __name__ == "__main__":
    print("===============================================================")
    print(" [CRM] Telecall CRM SaaS - Strictly Calling & Employee Tracking")
    print("===============================================================")
    print(" * Web Application: http://localhost:8000")
    print(" * Admin Portal:    http://localhost:8000/admin")
    print(" * Agent Workspace: http://localhost:8000/workspace")
    print(" * Super Admin:     http://localhost:8000/superadmin")
    print(" * Swagger Docs:    http://localhost:8000/docs")
    print("===============================================================")
    uvicorn.run("backend.app.main:app", host="0.0.0.0", port=8000, reload=True)
