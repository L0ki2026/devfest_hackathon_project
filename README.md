# NutriLens (DevFest hackathon)

Unified **web app + Python API**: the eatclean UI and the NutriLens backend run together on one server.

## Quick start

```bash
cd nutrilens/backend
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

API docs: http://localhost:8000/docs · Contract: [`nutrilens/API_CONTRACT.md`](nutrilens/API_CONTRACT.md)

## Layout

| Path | Role |
|------|------|
| `nutrilens/frontend/index.html` | Mobile web UI (Log, Quality, Gaps, Pantry) |
| `nutrilens/backend/` | FastAPI: USDA analysis, search, Gemini adapters |
| `server.js` | **Legacy** Node server (port 3000) — use FastAPI instead |

## Tests

```bash
cd nutrilens/backend && pytest -q
```

## Note on `tally.zip`

Older repo artifact at repo root; not part of the NutriLens runtime.