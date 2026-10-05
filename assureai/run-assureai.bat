@echo off
cd /d "%~dp0"

set ANTHROPIC_API_KEY=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

echo Starting AssureAI Backend and Frontend...
echo.

start "AssureAI Backend" powershell -NoExit -ExecutionPolicy Bypass -Command "cd backend; .\venv\Scripts\python.exe -m uvicorn app.main:app --port 8001"
timeout /t 3 /nobreak

start "AssureAI Frontend" cmd /k "cd frontend && npm run dev"

echo.
echo ======================================
echo Backend:  http://localhost:8001
echo Frontend: http://localhost:5174
echo ======================================
echo.
echo Both services are starting in separate windows...
