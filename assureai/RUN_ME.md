# Running AssureAI on a new laptop

AssureAI has two parts that run side by side:

| Part | Folder | Port | What it is |
|---|---|---|---|
| Backend | `backend/` | 8001 | Python (FastAPI) API with the agents and the Excel export |
| Frontend | `frontend/` | 5174 | React web app you use in the browser |

The frontend talks to the backend, so **both must be running**. If the "Pilot control"
dropdown is empty or you see a "status code 500" banner, the backend isn't running.

## 1. Install once

- **Python 3.12** (3.11 also works): https://www.python.org/downloads/. On Windows, tick
  "Add python.exe to PATH" in the installer.
- **Node.js 20 or newer** (LTS is fine): https://nodejs.org/
- **VS Code**: https://code.visualstudio.com/ (optional but recommended)

Check them in a terminal:

```
python --version
node --version
npm --version
```

(On Mac/Linux use `python3` instead of `python`.)

## 2. Open the project

Unzip `assureai.zip`, then in VS Code use **File > Open Folder** and pick the `assureai`
folder. Open two terminals with **Terminal > New Terminal** (use the `+` button for the
second one).

## 3. Start the backend (terminal 1)

### Windows (PowerShell)

```
cd backend
python -m venv venv
.\venv\Scripts\python.exe -m pip install -r requirements.txt
.\venv\Scripts\python.exe -m uvicorn app.main:app --port 8001
```

### Mac / Linux

```
cd backend
python3 -m venv venv
./venv/bin/python -m pip install -r requirements.txt
./venv/bin/python -m uvicorn app.main:app --port 8001
```

You only need the `python -m venv` and `pip install` lines the first time. Next time, just
run the last line. When it works you will see `Uvicorn running on http://127.0.0.1:8001`.
Leave this terminal open.

## 4. Start the frontend (terminal 2)

```
cd frontend
npm install
npm run dev
```

`npm install` is only needed the first time. When it works you will see
`Local: http://localhost:5174/`. Open **http://localhost:5174** in your browser.

## 5. Using the app

1. Type a **Reviewer ID** at the top (for example `j.smith`). Every approval is recorded
   under it.
2. **Step 1:** load a control (pick a pilot control, upload a RACM `.json`, or paste JSON),
   then click **Approve RACM Input**.
3. **Steps 2 to 7:** generate or review each step, edit if needed, and approve it. Each step
   stays locked until the one before it is approved. **Request Changes** needs a comment.
4. **Step 8 (Human Review):** Approve, Edit or Reject the control.
5. Once approved, **Download RACM Excel** appears.

The pilot controls are **synthetic test data**, not real clients.

## 6. Running the tests (optional)

Backend (from `backend/`, with the same Python as above):

```
.\venv\Scripts\python.exe -m pytest -q          # Windows
./venv/bin/python -m pytest -q                  # Mac / Linux
```

Frontend (from `frontend/`):

```
npm run test
```

## Troubleshooting

- **Dropdown empty / "status code 500"**: the backend isn't running. Start it (step 3).
- **"Port 8001 (or 5174) is already in use"**: close the other copy that is running, or
  restart your laptop.
- **PowerShell says scripts are disabled**: the commands above call `venv\Scripts\python.exe`
  directly, so no activation script is needed. Don't run `Activate.ps1`.
- **`python` not found on Windows**: reinstall Python and tick "Add python.exe to PATH", or
  try `py -3.12` instead of `python`.
- **`npm install` fails**: check your internet connection, and that Node is version 20 or
  newer (`node --version`).
- **Changed the backend code?** Stop it (Ctrl+C) and start it again.

## Notes

- Nothing is stored on a server or in a database. Reload the page and your work is gone, so
  download the Excel before closing.
- Nothing here calls an AI service or needs any account, key or internet connection once the
  dependencies are installed.
