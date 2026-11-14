# NutriLens — Cursor Backend Build Specification

> **Instructions to Cursor:** You are the backend engineer for NutriLens, a 48-hour Google DevFest hackathon project. Implement a **working Python FastAPI backend** matching this specification. The React frontend is being built independently by a teammate. Keep routes, JSON field names, and semantics stable. Do not generate the frontend. **Write code and tests, not only an implementation plan.** Favor a reliable, demonstrable end-to-end pipeline over elaborate architecture.

## 1. Product overview

**NutriLens** turns a photo of a grocery receipt, a grocery-list image, or a manually entered grocery basket into an interactive nutrition dashboard. Users can explore nutrition represented by purchased/available food, see which nutrients are relatively underrepresented, request ingredient additions, and generate meals from food they own. A post-workout endpoint suggests recovery-oriented meals given workout information and user preferences.

**Scientific integrity requirements:**
- Food in a grocery basket is **not** the same as food actually eaten. Never call grocery-basket gaps a diagnosed *deficiency* or treat total basket nutrients as daily intake.
- Nutrition estimates must be calculated deterministically in Python from reliable database values, **never invented by Gemini**.
- Gemini extracts grocery items from images and can propose meal combinations/explanations; backend validates every suggested ingredient and recalculates nutrient totals.
- The user must be able to confirm/edit extracted items and quantities before analysis. If quantity is not known, flag it as an assumption, not a fact.
- General wellness advice only; no medical diagnosis, individualized medical targets, or inappropriate certainty.

## 2. Stack and priorities

- Python 3.11+; FastAPI; Uvicorn; Pydantic v2; `httpx`; `python-multipart`; `pydantic-settings`; `pytest`/`pytest-asyncio`.
- Gemini: **official `google-genai` Python SDK** (`from google import genai`), not the older `google-generativeai` package. Use multimodal image understanding with structured JSON/Pydantic output. Read the currently installed SDK examples before coding against an API version; model name is configurable.
- Food nutrient data: **USDA FoodData Central** search (`/foods/search`) and food detail (`/food/{fdcId}`), with `FDC_API_KEY`. Prefer generic Foundation/SR Legacy foods over branded foods unless a branded match is explicitly requested. Use local caching, handle HTTP 429 and timeouts.
- SQLite for optional MVP persistence, but prioritize a stateless end-to-end flow. A lightweight cache (SQLite or JSON) is fine.
- No Apple Health connection in the MVP: workout metadata comes via user input. Preserve a clean input schema so a future iOS HealthKit companion app can send the same payload.
- Keep dependencies small; avoid unnecessary agent frameworks, vector stores, auth systems, payment integrations, and complex deployment infrastructure.

## 3. Directory structure

Create this layout in the repository (do not overwrite an existing frontend directory):

```text
nutrilens/
  backend/
    app/
      __init__.py
      main.py
      config.py
      schemas.py
      api/
        __init__.py
        routes.py
      services/
        __init__.py
        gemini_service.py
        usda_service.py
        matching.py
        nutrition.py
        recommendation.py
        meal_planner.py
      data/
        demo_foods.json
    tests/
      test_health.py
      test_nutrition.py
      test_routes.py
      test_matching.py
    requirements.txt
    .env.example
    README.md
  API_CONTRACT.md
```

`API_CONTRACT.md` must document exact request/response models, endpoints, error codes, and a curl example for each endpoint; it is the frontend team's source of truth. If a route/schema must change, update `API_CONTRACT.md` **at the same time** and clearly report the change.

## 4. Shared data models (use these exact names/fields)

Use Pydantic models and publish them in OpenAPI (`/docs`). Use consistent JSON snake_case fields; keep IDs stable and numeric quantities explicit.

```json
// BasketItem — used everywhere
{
  "id": "item_1",
  "name": "banana",
  "quantity": 3,
  "unit": "piece",
  "grams_per_unit": 118,
  "estimated": true
}
```

Rules:
- Accepted units: `g`, `kg`, `oz`, `lb`, `piece`, `cup`, `ml`, `l` where meaningful. Do not silently apply universal mass conversions for pieces/cups; conversions must be food-specific or explicitly provided. Unknown conversions -> `needs_confirmation`.
- For items given in `g`, canonical mass is the quantity. For non-mass units, convert with a verified food-specific conversion, a supplied `grams_per_unit`, or explicitly flagged demo assumption.
- `estimated` identifies inferred quantities or units, particularly for receipt entries.
- Never treat an unqualified receipt line (e.g., `BANANAS 2.49`) as 2.49 bananas.

```json
// WorkoutInput
{
  "type": "running",
  "duration_minutes": 45,
  "intensity": "moderate",
  "active_calories_kcal": null
}
```

Supported `intensity` values: `low`, `moderate`, `high`, `unknown`.

```json
// UserPreferences
{
  "diet": "vegetarian",
  "allergens": ["peanuts"],
  "goal": "general_wellness",
  "servings": 1,
  "budget_usd": null
}
```

Possible `goal` values: `general_wellness`, `muscle_gain`, `endurance_recovery`, `weight_management`. These are **meal-planning preferences**, not clinical profiles.

Define reusable `Nutrients` fields: `calories_kcal`, `protein_g`, `carbs_g`, `fat_g`, `fiber_g`, `calcium_mg`, `iron_mg`, `potassium_mg`, `vitamin_c_mg` (numeric when known, `null` when unavailable). Do not replace missing data with zero. Include `data_completeness`/warnings where appropriate.

## 5. API endpoints (implement in this order)

All application endpoints are under `/api`. Configure CORS with `FRONTEND_ORIGINS`, default `http://localhost:3000,http://localhost:5173` for local dev only.

### A. `GET /api/health`

Returns `200 {"status":"ok","service":"nutrilens-backend"}` without requiring API keys. Include an optional safe indicator of external configuration, but **never** reveal key values.

### B. `POST /api/parse-groceries` — multipart image upload

Input: `file` (`image/jpeg`, `image/png`, or `image/webp`; 10 MB max). Validate size/type, handle non-images, failures and timeouts.

Response shape:

```json
{
  "items": [
    {"id":"item_1","name":"banana","quantity":3,"unit":"piece","grams_per_unit":null,"estimated":true},
    {"id":"item_2","name":"milk","quantity":1,"unit":"l","grams_per_unit":null,"estimated":false}
  ],
  "needs_confirmation": true,
  "warnings": ["Banana count estimated; please verify."],
  "source": "gemini"
}
```

Use Gemini structured output to extract grocery food names, amounts, and units; no freeform prose parsing as the main path. Ignore receipt totals, tax, nonfood merchandise and duplicate subtotal lines. Return quantities as `null` if unknown **and** require user confirmation; implement the schema accordingly rather than falsely asserting a value. Do not hallucinate a food not visible in the image. If missing key, return `503` with clear JSON error (unless `DEMO_MODE=true`, where fixture-driven parsing is clearly marked `source: "demo"`).

### C. `POST /api/analyze-basket` — core deterministic nutrition endpoint

Input:

```json
{
  "items": [
    {"id":"item_1","name":"banana","quantity":3,"unit":"piece","grams_per_unit":118,"estimated":true},
    {"id":"item_2","name":"plain greek yogurt","quantity":500,"unit":"g","grams_per_unit":null,"estimated":false}
  ],
  "preferences": {"diet":"vegetarian","allergens":[],"goal":"general_wellness","servings":1,"budget_usd":null}
}
```

Response:

```json
{
  "items": [
    {
      "id":"item_1",
      "input_name":"banana",
      "matched_name":"Bananas, raw",
      "fdc_id":123456,
      "match_status":"matched",
      "match_confidence":0.95,
      "mass_g":354,
      "nutrients":{"calories_kcal":315,"protein_g":3.9,"carbs_g":81,"fat_g":1.2,"fiber_g":9.2,"calcium_mg":18,"iron_mg":0.9,"potassium_mg":1268,"vitamin_c_mg":31}
    }
  ],
  "totals":{"calories_kcal":315,"protein_g":3.9,"carbs_g":81,"fat_g":1.2,"fiber_g":9.2,"calcium_mg":18,"iron_mg":0.9,"potassium_mg":1268,"vitamin_c_mg":31},
  "warnings":[],
  "unmatched_items":[],
  "disclaimer":"Estimated nutrients available in this grocery basket, not nutrients consumed."
}
```

**These sample nutrient numbers and `fdc_id` are placeholders for schema illustration only. Do not hardcode them as facts.** Actual values must come from USDA response/validated demo fixtures and mass-based math.

Implementation rules:
- USDA search -> select plausible food matching physical form (raw/cooked, whole/skim, etc.) -> fetch nutrient details. Show match confidence and matched description so users can correct errors.
- Normalize food names carefully; prefer simple, generic items. Do not claim 100% matching confidence. For ambiguous matches, return `needs_confirmation`/candidates rather than silently choosing branded cereal or the wrong product.
- USDA nutrients are often expressed per 100 g; compute `amount = value_per_100g * mass_g / 100`, handling source data forms appropriately. Normalize nutrient units; use verified nutrient IDs/names and unit mappings, do not assume every nutrient uses the same unit.
- Distinguish unknown nutrients (`null`) from true zeros. Sum known contributions but indicate incomplete totals when an ingredient lacks data.
- Handle repeated items, negative/zero quantities, invalid units, missing food matches, and unreachable USDA gracefully. Preserve partial results with warnings where defensible, or return structured errors.

### D. `POST /api/recommend-additions`

Input: `{ "items": [BasketItem...], "preferences": UserPreferences, "focus_nutrients": ["protein_g","iron_mg"] }`.

Return 3–5 addition suggestions with: `name`, `reason`, `estimated_nutrients_per_serving`, `suggested_quantity`, `unit`, and `evidence_source`. Use a small, curated list of common ingredients (beans, lentils, tofu, leafy greens, yogurt, oats, etc.), filter diet/allergens, retrieve USDA nutrient data, and rank for the requested focus nutrients. **Do not infer that a person is deficient just because a basket has little iron.** If no explicit `focus_nutrients`, rank relative basket variety/representation and state that this is not a medical nutritional assessment. Budget is a soft preference unless real item prices are available; don't invent prices.

### E. `POST /api/plan-meal`

Input: `{ "items": [BasketItem...], "preferences": UserPreferences, "meal_type":"lunch", "focus_nutrients":["protein_g"] }`. Allow `meal_type` values `breakfast`, `lunch`, `dinner`, `snack`.

Return 1–3 meal candidates with `title`, `ingredients` (food name, amount, unit), `instructions`, `nutrition` (calculated by backend), `why_this_meal`, `missing_ingredients` (normally empty), and `warnings`.

Use Gemini to suggest structured recipes **only with available foods**, but reject allergens, dietary conflicts, quantities above inventory and invented foods. Recompute nutrients in Python. A deterministic fallback should provide at least one sensible demo meal when Gemini is unavailable in `DEMO_MODE=true`.

### F. `POST /api/post-workout-meal`

Input:

```json
{
  "workout":{"type":"running","duration_minutes":45,"intensity":"moderate","active_calories_kcal":null},
  "items":[
    {"id":"item_1","name":"banana","quantity":2,"unit":"piece","grams_per_unit":118,"estimated":false},
    {"id":"item_2","name":"plain greek yogurt","quantity":500,"unit":"g","grams_per_unit":null,"estimated":false},
    {"id":"item_3","name":"oats","quantity":200,"unit":"g","grams_per_unit":null,"estimated":false}
  ],
  "preferences":{"diet":"vegetarian","allergens":[],"goal":"endurance_recovery","servings":1,"budget_usd":null}
}
```

Return: `workout_summary`, `recovery_priorities` (e.g., protein, carbs, fluids), `meals` (same verified schema as `/api/plan-meal`), `assumptions`, `disclaimer`.

Decision flow:
1. Small **configurable, non-clinical rule layer** decides qualitative recovery priorities from workout type, duration, intensity, and goal. Do **not** calculate personalized nutrient prescriptions from workout type alone, assume burned calories should be fully eaten back, or invent evidence-backed precise targets.
2. Optionally use Gemini to pick a realistic combination from the user's available ingredients and explain the selection.
3. Enforce diet/allergens/inventory constraints and recalculate macros in Python using USDA data.
4. If an ingredient is missing or insufficient, clearly separate optional grocery additions from usable current-inventory meals.
5. Clearly disclose limitations: general wellness suggestions, not medical advice; needs vary by individual and overall diet.

## 6. Gemini behavior

- Use `GEMINI_API_KEY` and configurable `GEMINI_MODEL` env vars.
- Pydantic/JSON schema response validation on every Gemini output; retry once after invalid structured output, then return a controlled error/fallback.
- Gemini may identify foods, suggest candidate recipes, and explain combinations; **Gemini must not supply trusted nutrient values**.
- For image upload, make no assumptions about price-as-quantity and avoid adding unseen items.
- For meal planning, only use confirmed available inventory; reject allergen/diet conflicts and unsupported ingredient quantities.
- Limit token usage, request count, and timeouts for hackathon reliability. Do not log secrets, raw personally identifiable data, or full uploaded images.

## 7. USDA FoodData Central behavior

- Environment key: `FDC_API_KEY`. Use `httpx.AsyncClient` and sane timeouts.
- Search generic food names; fetch selected food's detailed nutrients; normalize per-100g data using accurate USDA metadata.
- Cache by normalized query and FDC ID, even if initially in-process; ideally add lightweight persistent caching.
- Add graceful errors for 401/403, 429, 5xx, network errors, and no results.
- For local demo, include a **small explicitly labeled offline dataset** containing nutrients per 100 g for about 10–15 standard foods. Demo data is approximate/not a live USDA response. Never silently switch live data to fixtures: mark `source: "demo"` and return a warning.
- Note in the README: obtain a key at https://fdc.nal.usda.gov/api-guide/ ; `DEMO_KEY` is for low-volume experiments only.

## 8. Validation / security / developer experience

- Use `DEMO_MODE=true` explicitly for offline fallback; default `false`. When APIs are unconfigured and not in demo mode, explain failure clearly instead of pretending to succeed.
- Reject invalid/oversized files, dangerous formats, unsupported quantities, and unreasonable item list sizes (e.g., max 100 items).
- Return consistent error JSON (`detail` or `{ "error": {"code": ..., "message": ...}}`) and document it.
- Centralized config with `.env.example`, safe `.gitignore`, no secret keys in source.
- Default local server `http://localhost:8000`; FastAPI OpenAPI docs at `/docs`.
- Add `README.md`: venv setup, `pip install -r requirements.txt`, creating `.env`, running `uvicorn app.main:app --reload`, testing with `pytest`, and copy-paste curl samples.
- All browser-facing responses should be JSON, including errors. Support local frontend dev with explicit CORS origins.
- Use conventional helpful HTTP statuses (400/422 user data, 413 oversized upload, 503 unavailable upstream).

## 9. Testing — required before saying this is complete

Unit tests (mock Gemini and USDA; no external API calls in CI):
- `GET /api/health` returns success.
- Weight/units and per-100g math: e.g. 250 g food with 10 g protein/100 g = 25 g protein.
- Missing data stays missing rather than becoming fabricated zero.
- Allergen exclusions and vegetarian filtering.
- Extracted receipt item with missing quantity stays unconfirmed.
- A mismatched recipe with ingredient not in stock is rejected.
- Endpoints validate correct request/response shapes.
- Graceful API failure and demo mode behavior.

Add an integration-style test: manual basket -> nutrition analysis -> meal recommendation using a deterministic stubbed USDA dataset, proving the frontend contract is actually usable.

## 10. Acceptance criteria — finish these before polishing

1. Running `uvicorn app.main:app --reload` starts the backend and `/docs` loads.
2. `/api/health` works without API keys.
3. With keys configured, a receipt or grocery-list image produces structured extractable grocery items for human confirmation.
4. A **manual grocery basket works end to end even without image parsing**.
5. Basket nutrition math is deterministic, auditable, and includes provenance/uncertainty.
6. Meal and post-workout endpoints work and never quietly violate known dietary/allergy constraints.
7. Endpoint JSON contracts are stable and written into top-level `API_CONTRACT.md`.
8. Tests run successfully; `README.md` contains exact startup and sample requests.
9. No frontend files are generated; no real secrets are committed.

## 11. Implementation order for Cursor

**Phase 1 (highest priority):** scaffold FastAPI/config/Pydantic, `/api/health`, manual `/api/analyze-basket`, USDA adapter, demo fixtures, unit tests, `API_CONTRACT.md`.

**Phase 2:** `/api/parse-groceries` with Gemini image structured extraction; safeguards for ambiguous quantities.

**Phase 3:** `/api/plan-meal` and `/api/post-workout-meal` with validated suggestions and Python-calculated nutrients.

**Phase 4:** `/api/recommend-additions`, caching, full integration tests, README polish.

After every phase, run tests and correct failures. If time is tight, prioritize **one working vertical slice** over partially implementing everything.

## 12. Completion report Cursor should give me

At the end, report:
1. Exact files created/modified.
2. Commands to start and test backend.
3. Whether each endpoint is **working live**, **working in demo mode**, or **not implemented**.
4. Required environment variables and where to obtain keys.
5. Remaining limitations and known bugs.
6. Any changes to the API contract that the frontend developer must know.

**Start implementing now. Do not stop at planning.**

---

### Reference documentation

- Gemini official Python SDK: https://ai.google.dev/gemini-api/docs/libraries
- Gemini structured output: https://ai.google.dev/gemini-api/docs/structured-output
- USDA FoodData Central: https://fdc.nal.usda.gov/api-guide/
- FastAPI: https://fastapi.tiangolo.com/
