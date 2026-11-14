# Baskt Backend

FastAPI backend for grocery basket nutrition analysis (Google DevFest hackathon).

## Setup

```bash
cd baskt/backend
python3.11 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

Edit `.env`:

- `DEMO_MODE=true` — offline demo nutrients (no USDA key required for development/tests)
- `FDC_API_KEY` — [USDA FoodData Central API key](https://fdc.nal.usda.gov/api-guide/) (`DEMO_KEY` is for low-volume experiments only)
- `GEMINI_API_KEY` — required later for image parsing / meal suggestions (Phase 2+)
- `FRONTEND_ORIGINS` — CORS, default `http://localhost:3000,http://localhost:5173`

## Run

```bash
source .venv/bin/activate
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

Open http://localhost:8000/docs

## Test

```bash
pytest -q
```

Tests use `DEMO_MODE=true` and do not call external APIs.

## Sample requests

Health:

```bash
curl -s http://localhost:8000/api/health | jq
```

Analyze basket (demo mode):

```bash
curl -s -X POST http://localhost:8000/api/analyze-basket \
  -H 'Content-Type: application/json' \
  -d '{
    "items": [
      {"id":"item_1","name":"banana","quantity":3,"unit":"piece","grams_per_unit":118,"estimated":true},
      {"id":"item_2","name":"plain greek yogurt","quantity":500,"unit":"g","grams_per_unit":null,"estimated":false}
    ],
    "preferences": {"diet":"vegetarian","allergens":[],"goal":"general_wellness","servings":1,"budget_usd":null}
  }' | jq
```

API contract for the frontend team: [`../API_CONTRACT.md`](../API_CONTRACT.md).