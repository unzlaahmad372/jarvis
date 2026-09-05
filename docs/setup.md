# JARVIS — Local Setup Guide

## Prerequisites

| Requirement | Version | Notes |
|---|---|---|
| Python | 3.12+ | `py -3.12 --version` |
| Node.js | 20 LTS | For frontend (Phase 0 shell) |
| Ollama | Latest | https://ollama.com |
| Git | Any | |

## 1. Clone / open the project

```bash
cd C:\Users\<you>\Projects\jarvis
```

## 2. Create the virtual environment

**Windows PowerShell:**
```powershell
py -3.12 -m venv .venv
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass  # if needed
.\.venv\Scripts\Activate.ps1
```

**Windows Command Prompt:**
```bat
py -3.12 -m venv .venv
.venv\Scripts\activate.bat
```

**Linux / WSL / macOS:**
```bash
python3.12 -m venv .venv
source .venv/bin/activate
```

## 3. Install backend dependencies

```bash
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
```

## 4. Verify environment

```bash
python --version          # should show Python 3.12.x
python -m pip --version
python -c "import sys; print(sys.executable)"  # should point inside .venv
```

## 5. Configure environment

```bash
copy .env.example .env    # Windows
cp .env.example .env      # Linux/macOS
```

Edit `.env` and set at minimum:
```
JARVIS_LLM_MODEL=llama3.2
JARVIS_OLLAMA_URL=http://127.0.0.1:11434
```

## 6. Install and start Ollama

Download from https://ollama.com and install.

Pull the configured model:
```bash
ollama pull llama3.2
```

Verify Ollama is running:
```bash
ollama list
```

## 7. Run backend tests

```bash
python -m pytest tests/ -v
```

## 8. Start the backend

```bash
python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

Or using the project script (after install):
```bash
jarvis
```

## 9. Verify health endpoints

```
GET http://127.0.0.1:8000/health/live
GET http://127.0.0.1:8000/health/ready
GET http://127.0.0.1:8000/health/dependencies
```

## 10. Frontend (Phase 0 shell — coming next)

```bash
cd frontend
npm install
npm run dev
```

Open http://127.0.0.1:5173

## VS Code setup

1. Open the `jarvis` folder
2. `Ctrl+Shift+P` → `Python: Select Interpreter`
3. Choose `.venv\Scripts\python.exe`

## Deactivate

```bash
deactivate
```

## Troubleshooting

**"Ollama is not reachable at 127.0.0.1:11434"**
→ Start Ollama: open the Ollama application or run `ollama serve`

**"Model 'llama3.2' not found"**
→ Run `ollama pull llama3.2`

**PowerShell activation blocked**
→ Run `Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass` first

**Import errors after install**
→ Ensure `.venv` is activated: `python -c "import sys; print(sys.executable)"` should show `.venv`
