@echo off
rem Starts the AssureAI backend and frontend in two windows.
rem
rem First time only (see RUN_ME.md): create backend\venv and run npm install in frontend.
rem
rem Optional AI tidy-up of the HOW answer: set ANTHROPIC_API_KEY as a Windows environment
rem variable (never write the key into this file or anywhere in the project folder).
rem   setx ANTHROPIC_API_KEY "your-key"      (then open a new window)
rem Without it the app works fully; it just uses its built-in rules instead.
rem Optional: set ASSUREAI_CONDENSE=1 to shorten extracted answers to short phrases.

cd /d "%~dp0"

if not exist "backend\venv\Scripts\python.exe" (
  echo backend\venv not found. Follow the "Start the backend" steps in RUN_ME.md first.
  pause
  exit /b 1
)
if not exist "frontend\node_modules" (
  echo frontend\node_modules not found. Run "npm install" in the frontend folder first.
  pause
  exit /b 1
)

start "AssureAI Backend" cmd /k "cd /d %~dp0backend && venv\Scripts\python.exe -m uvicorn app.main:app --port 8001"
timeout /t 3 /nobreak >nul
start "AssureAI Frontend" cmd /k "cd /d %~dp0frontend && npm run dev"

echo.
echo Backend:  http://localhost:8001
echo Frontend: http://localhost:5174   (open this one in your browser)
echo.
echo Both are starting in separate windows. Close those windows to stop the app.
