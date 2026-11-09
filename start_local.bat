@echo off
title J.A.R.V.I.S. AI - Local Startup
echo ==========================================================
echo              J.A.R.V.I.S. AI LOCAL STARTUP                  
echo ==========================================================

if exist .venv goto VENV_EXISTS
echo [*] Creating Python virtual environment .venv...
python -m venv .venv
if errorlevel 1 (
    echo [ERROR] Failed to create virtual environment. Ensure Python is installed.
    pause
    exit /b 1
)
:VENV_EXISTS


echo [*] Activating virtual environment and installing dependencies...
call .venv\Scripts\activate
pip install -r simulation/mock-services/requirements.txt
pip install -r backend/requirements.txt

echo [*] Launching simulated microservice cluster...
start /min "J.A.R.V.I.S.: Notification Service" cmd /c "set SERVICE_NAME=notification-service&&set PORT=8005&&.venv\Scripts\python.exe simulation/mock-services/app.py"
start /min "J.A.R.V.I.S.: Payment Service" cmd /c "set SERVICE_NAME=payment-service&&set PORT=8004&&set DOWNSTREAM_URLS=http://localhost:8005&&.venv\Scripts\python.exe simulation/mock-services/app.py"
start /min "J.A.R.V.I.S.: Order Service" cmd /c "set SERVICE_NAME=order-service&&set PORT=8003&&set DOWNSTREAM_URLS=http://localhost:8004&&.venv\Scripts\python.exe simulation/mock-services/app.py"
start /min "J.A.R.V.I.S.: User Service" cmd /c "set SERVICE_NAME=user-service&&set PORT=8002&&.venv\Scripts\python.exe simulation/mock-services/app.py"
start /min "J.A.R.V.I.S.: API Gateway" cmd /c "set SERVICE_NAME=api-gateway&&set PORT=8001&&set DOWNSTREAM_URLS=http://localhost:8002,http://localhost:8003&&.venv\Scripts\python.exe simulation/mock-services/app.py"

echo [+] Mock cluster running (api-gateway:8001, user:8002, order:8003, payment:8004, notification:8005)

echo [*] Launching FastAPI SRE Backend...
cd backend
start "J.A.R.V.I.S.: FastAPI SRE Agent" cmd /c "set DATABASE_URL=sqlite:///./jarvis.db&&set OLLAMA_HOST=http://localhost:11434&&..\.venv\Scripts\python.exe -m uvicorn app.main:app --host 0.0.0.0 --port 8000"
cd ..

echo [+] FastAPI backend is starting...

echo [*] Launching Next.js Control Dashboard...
cd frontend
start "J.A.R.V.I.S.: Next.js Dashboard" cmd /c "npm run dev"
cd ..

echo [+] Next.js dev server is starting...
echo ==========================================================
echo  SETUP COMPLETE!
echo  -^> SRE Backend API: http://localhost:8000
echo  -^> SRE Dashboard: http://localhost:3000
echo  -^> Ensure Ollama is running and has qwen2.5:3b pulled:
echo     ollama pull qwen2.5:3b
echo ==========================================================
pause
