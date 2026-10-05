# Running AssureAI on a new laptop

AssureAI has two parts that run side by side:

| Part | Folder | Port | What it is |
|---|---|---|---|
| Backend | `backend/` | 8001 | Python (FastAPI) API with the agents and the Excel export |
| Frontend | `frontend/` | 5174 | React web app you use in the browser |

The frontend talks to the backend, so **both must be running**. If an upload fails
with a "status code 500" or "Network Error" message, the backend isn't running.

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

**Shortcut on Windows:** after the one-time setup in steps 3 and 4, double-click `run-assureai.bat`
to start both parts in two windows.

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
2. **Step 1:** load a control (upload an Excel RACM `.xlsx` or a `.json` record, or paste JSON),
   then click **Approve RACM Input**.
   To try it with made-up data, upload the files in the `samples/` folder (see `samples/README.md`).
3. **Steps 2 to 7:** generate or review each step, edit if needed, and approve it. Each step
   stays locked until the one before it is approved. **Request Changes** needs a comment.
   In step 3 you can upload the transcript as a Word `.docx` or a `.txt` file.
4. **Step 8 (Human Review):** Approve, Edit or Reject the control.
5. Once approved, **Download RACM Excel** appears.

The files in `samples/` are **synthetic test data**, not real clients.

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

- **Upload fails with "status code 500" / "Network Error"**: the backend isn't running. Start it (step 3).
- **"Port 8001 (or 5174) is already in use"**: close the other copy that is running, or
  restart your laptop.
- **PowerShell says scripts are disabled**: the commands above call `venv\Scripts\python.exe`
  directly, so no activation script is needed. Don't run `Activate.ps1`.
- **`python` not found on Windows**: reinstall Python and tick "Add python.exe to PATH", or
  try `py -3.12` instead of `python`.
- **`npm install` fails**: check your internet connection, and that Node is version 20 or
  newer (`node --version`).
- **Changed the backend code?** Stop it (Ctrl+C) and start it again.

## Uploading your own files

- **RACM (step 1):** an Excel `.xlsx` using the standard headers (the same ones the app's own
  Excel export uses, so an exported RACM can be uploaded again), or a `.json` record. Only the
  first control row is read. See `samples/README.md` for the full header list. Old `.xls` files
  must be saved as `.xlsx` first.
- **Transcript (step 3):** a Word `.docx` or a plain `.txt` file, with lines like
  `[L01] Interviewer: ...` / `[L02] Interviewee: ...`. Old `.doc` files must be saved as `.docx`.

## How the structured documentation reads

Each of the six attributes is written as a short documentation phrase rather than a quote of the
interview. For example:

| | |
|---|---|
| **When** | `Weekly` (from "every Thursday"), `Yearly`, `Twice a year`, or `Triggered every time HR notifies of a new starter` |
| **Who** | `AP Supervisor and Finance Manager` |
| **Why** | `To prevent unauthorised, duplicate or incorrect payments to suppliers` |
| **Where** | `Finance System`, `ServiceNow` |

Every word comes from the interviewee's answer, and if a field can't be condensed confidently the
original wording is kept. The full conversational answer is always available under **View source**.

## Optional settings (environment variables)

Nothing here is required. Never put a key in a file inside the project folder.

| Variable | Effect |
|---|---|
| `ANTHROPIC_API_KEY` | If set, the HOW answer is tidied by Claude. If not set, built-in rules are used. This sends transcript text to an outside service, so check your data rules first. |
| `ANTHROPIC_MODEL` | Which Claude model to use (default `claude-opus-5`). |
| `ASSUREAI_CONDENSE=0` | Turns off the short-phrase wording of the structured documentation (see below) and keeps the full answers. On by default. |

On Windows, set a key once with `setx ANTHROPIC_API_KEY "your-key"` and open a new window.

## Notes

- Nothing is stored on a server or in a database. Reload the page and your work is gone, so
  download the Excel before closing.
- With no `ANTHROPIC_API_KEY` set, nothing calls an AI service, and no account or internet
  connection is needed once the dependencies are installed.
