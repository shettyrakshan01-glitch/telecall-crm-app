@echo off
title TeleCall CRM Server
cd /d "%~dp0"
echo ========================================================
echo        Starting TeleCall CRM SaaS Server...
echo ========================================================
echo Computer Browser: http://localhost:8000
echo Android Mobile (Same Wi-Fi): http://192.168.1.116:8000
echo ========================================================
.\venv\Scripts\python run.py
pause
