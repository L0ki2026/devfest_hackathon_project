# Baskt (DevFest hackathon)

Unified **web app + Python API**: the baskt UI and the Baskt backend run together on one server.

## Quick start

```bash
cd baskt/backend
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

In `.env` (minimum for offline dev):

```env
DEMO_MODE=true
```

Optional keys:

- `GEMINI_API_KEY` — photo identify + workout suggestions ([Google AI Studio](https://aistudio.google.com/apikey))
- `FDC_API_KEY` or `USDA_API_KEY` — live USDA ([FoodData Central](https://fdc.nal.usda.gov/api-key-signup.html))

Run:

```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

Open **http://localhost:8000** (UI + `/api/*`).

API docs: http://localhost:8000/docs · Contract: [`baskt/API_CONTRACT.md`](baskt/API_CONTRACT.md)

## Layout

| Path | Role |
|------|------|
| `baskt/frontend/index.html` | Mobile web UI (Log, Quality, Gaps, Pantry) |
| `baskt/backend/` | FastAPI: USDA analysis, search, Gemini adapters |
| `server.js` | **Legacy** Node server (port 3000) — use FastAPI instead |

## Tests

```bash
cd baskt/backend && pytest -q
```