# J.A.R.V.I.S. AI - Local Development Startup Script
# This runs the entire SRE simulation environment, backend agent, and frontend dashboard on localhost without requiring Docker.

Write-Host "==========================================================" -ForegroundColor Cyan
Write-Host "             J.A.R.V.I.S. AI LOCAL STARTUP                  " -ForegroundColor Cyan
Write-Host "==========================================================" -ForegroundColor Cyan

# 1. Create Python virtual environment if it doesn't exist
if (-not (Test-Path ".venv")) {
    Write-Host "[*] Creating Python virtual environment (.venv)..." -ForegroundColor Yellow
    Start-Process python -ArgumentList "-m venv .venv" -NoNewWindow -Wait
}

# 2. Install dependencies in virtual environment
Write-Host "[*] Upgrading pip and installing Python dependencies..." -ForegroundColor Yellow
Start-Process .venv/Scripts/pip -ArgumentList "install --upgrade pip" -NoNewWindow -Wait
Start-Process .venv/Scripts/pip -ArgumentList "install -r simulation/mock-services/requirements.txt -r backend/requirements.txt" -NoNewWindow -Wait

# 3. Start Mock Services in background
Write-Host "[*] Launching simulated microservice cluster on localhost..." -ForegroundColor Yellow

# Notification Service (Port 8005)
Start-Process .venv/Scripts/python.exe -ArgumentList "simulation/mock-services/app.py" -Environment @{
    SERVICE_NAME = "notification-service"
    PORT = "8005"
} -WindowStyle Minimized

# Payment Service (Port 8004)
Start-Process .venv/Scripts/python.exe -ArgumentList "simulation/mock-services/app.py" -Environment @{
    SERVICE_NAME = "payment-service"
    PORT = "8004"
    DOWNSTREAM_URLS = "http://localhost:8005"
} -WindowStyle Minimized

# Order Service (Port 8003)
Start-Process .venv/Scripts/python.exe -ArgumentList "simulation/mock-services/app.py" -Environment @{
    SERVICE_NAME = "order-service"
    PORT = "8003"
    DOWNSTREAM_URLS = "http://localhost:8004"
} -WindowStyle Minimized

# User Service (Port 8002)
Start-Process .venv/Scripts/python.exe -ArgumentList "simulation/mock-services/app.py" -Environment @{
    SERVICE_NAME = "user-service"
    PORT = "8002"
} -WindowStyle Minimized

# API Gateway (Port 8001)
Start-Process .venv/Scripts/python.exe -ArgumentList "simulation/mock-services/app.py" -Environment @{
    SERVICE_NAME = "api-gateway"
    PORT = "8001"
    DOWNSTREAM_URLS = "http://localhost:8002,http://localhost:8003"
} -WindowStyle Minimized

Write-Host "[+] Mock services running (api-gateway:8001, user:8002, order:8003, payment:8004, notification:8005)" -ForegroundColor Green

# 4. Start FastAPI Backend (Port 8000)
Write-Host "[*] Launching FastAPI Backend on Port 8000..." -ForegroundColor Yellow
Start-Process ../.venv/Scripts/python.exe -ArgumentList "-m uvicorn app.main:app --host 0.0.0.0 --port 8000" -WorkingDirectory "backend" -Environment @{
    DATABASE_URL = "sqlite:///./jarvis.db"
    OLLAMA_HOST = "http://localhost:11434"
} -WindowStyle Normal

Write-Host "[+] FastAPI Backend is starting..." -ForegroundColor Green

# 5. Start Next.js Frontend (Port 3000)
Write-Host "[*] Launching Next.js Control Dashboard..." -ForegroundColor Yellow
Start-Process npm -ArgumentList "run dev" -WorkingDirectory "frontend" -WindowStyle Normal

Write-Host "[+] Next.js dev server is starting..." -ForegroundColor Green
Write-Host "==========================================================" -ForegroundColor Green
Write-Host " SETUP COMPLETE! " -ForegroundColor Green
Write-Host " -> Backend API: http://localhost:8000" -ForegroundColor Green
Write-Host " -> Frontend Control Center: http://localhost:3000" -ForegroundColor Green
Write-Host " -> Ensure Ollama is running and has qwen2.5:3b pulled (ollama pull qwen2.5:3b)" -ForegroundColor Yellow
Write-Host "==========================================================" -ForegroundColor Green
