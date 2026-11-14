# Baskt API Contract

Base URL (local): `http://localhost:8000`

All application routes are under `/api`. JSON bodies use **snake_case**. OpenAPI docs: `http://localhost:8000/docs`

## Shared models

### `BasketItem`

| Field | Type | Notes |
|-------|------|-------|
| `id` | string | Stable client-assigned id |
| `name` | string | Food name |
| `quantity` | number \| null | Null if unknown |
| `unit` | string | `g`, `kg`, `oz`, `lb`, `piece`, `cup`, `ml`, `l` |
| `grams_per_unit` | number \| null | Required for `piece`/`cup` when no food default |
| `estimated` | boolean | Inferred quantity/unit |

### `UserPreferences`

| Field | Type |
|-------|------|
| `diet` | string |
| `allergens` | string[] |
| `goal` | `general_wellness` \| `muscle_gain` \| `endurance_recovery` \| `weight_management` |
| `servings` | integer |
| `budget_usd` | number \| null |

### `Nutrients`

Numeric when known, `null` when unavailable (never fabricate `0` for missing data).

Fields: `calories_kcal`, `protein_g`, `carbs_g`, `fat_g`, `fiber_g`, `calcium_mg`, `iron_mg`, `potassium_mg`, `vitamin_c_mg`

### Errors

User-facing errors may use FastAPI `detail` as either a string or:

```json
{
  "error": {
    "code": "usda_unavailable",
    "message": "Human-readable message"
  }
}
```

Validation failures: HTTP `422` with `detail` (array) and optional `error.code` = `validation_error`.

---

## Phase 1 (implemented)

### `GET /api/health`

**Response `200`**

```json
{
  "status": "ok",
  "service": "baskt-backend",
  "demo_mode": false,
  "gemini_configured": false,
  "usda_configured": true
}
```

Does not expose secret values.

```bash
curl -s http://localhost:8000/api/health | jq
```

---

### `POST /api/analyze-basket`

Deterministic nutrition for a confirmed grocery basket.

**Request**

```json
{
  "items": [
    {
      "id": "item_1",
      "name": "banana",
      "quantity": 3,
      "unit": "piece",
      "grams_per_unit": 118,
      "estimated": true
    }
  ],
  "preferences": {
    "diet": "vegetarian",
    "allergens": [],
    "goal": "general_wellness",
    "servings": 1,
    "budget_usd": null
  }
}
```

**Response `200`**

```json
{
  "items": [
    {
      "id": "item_1",
      "input_name": "banana",
      "matched_name": "Bananas, raw",
      "fdc_id": 900001,
      "match_status": "matched",
      "match_confidence": 0.95,
      "mass_g": 354,
      "nutrients": { "calories_kcal": 315.06, "protein_g": 3.89, "...": "..." },
      "warnings": []
    }
  ],
  "totals": { "calories_kcal": 315.06, "protein_g": 3.89, "...": "..." },
  "warnings": [],
  "unmatched_items": [],
  "disclaimer": "Estimated nutrients available in this grocery basket, not nutrients consumed.",
  "data_source": "demo"
}
```

`match_status`: `matched` \| `needs_confirmation` \| `unmatched`

`data_source`: `usda` \| `demo` (demo when `DEMO_MODE=true` or no `FDC_API_KEY`)

**Errors**

| Status | Code | When |
|--------|------|------|
| 400 | `too_many_items` | More than 100 items |
| 422 | `empty_basket` / validation | Empty items or invalid schema |
| 503 | `usda_unavailable` | No API key and `DEMO_MODE` not enabled |
| 503 | `usda_*` | Upstream USDA failures |

```bash
curl -s -X POST http://localhost:8000/api/analyze-basket \
  -H 'Content-Type: application/json' \
  -d '{
    "items": [
      {"id":"item_1","name":"banana","quantity":3,"unit":"piece","grams_per_unit":118,"estimated":true}
    ]
  }' | jq
```

---

## baskt UI compatibility (same server)

These routes power the mobile web UI at `http://localhost:8000/` and match the former Node `server.js` contract:

| Method | Path | Notes |
|--------|------|--------|
| GET | `/api/search?q=` | USDA + Open Food Facts, baskt food objects |
| POST | `/api/identify` | JSON `{image, mime}` base64; needs `GEMINI_API_KEY` (or demo names) |
| POST | `/api/workout` | JSON `{text, pantry[]}` |
| POST | `/api/pantry-analyze` | JSON `{names[]}` → Baskt `analyze-basket` (100 g each) |

---

## Phase 2–4 (not implemented yet)

The following routes are specified in the product spec but are **not** available in Phase 1:

- `POST /api/parse-groceries`
- `POST /api/recommend-additions`
- `POST /api/plan-meal`
- `POST /api/post-workout-meal`

Frontend should treat them as upcoming; Phase 1 supports manual basket entry via `analyze-basket` only.