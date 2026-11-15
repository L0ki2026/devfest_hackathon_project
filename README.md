# Baskt

Day-by-day nutrition journal with USDA/Open Food Facts search, barcode lookup, a pantry, nutrient gaps, and post-workout meal suggestions on the **Gaps** tab.

## Setup

1. Get a Gemini key: https://aistudio.google.com/apikey  
2. Get a USDA key: https://fdc.nal.usda.gov/api-key-signup  
3. Copy `.env.example` to `.env` and paste both keys in.  
4. Run `npm install` then `npm start`, and open http://localhost:3000  

API keys stay on the server. The browser calls `/api/search`, `/api/barcode/:code`, and `/api/workout-meal` (`/api/identify` exists on the server but has no UI yet).

## Tests

`npm test` runs the unit tests in `test/` with Node's built-in test runner (no extra dependencies). They cover local-date handling (including UTC-offset and DST boundaries), per-day entries, totals, history, and data migration in `public/journal.js`.

## How data is saved

Everything is stored in the browser's `localStorage` under `baskt.v2`:

- `pantry`: foods you have at home (`{id, foodId, name}`). Not tied to a date.
- `dailyLogs`: foods you ate, keyed by **local** date (`YYYY-MM-DD`). Each entry stores the amount, unit (serving, g, oz), optional meal, timestamp, data source, and a nutrient snapshot for the amount eaten, so past totals stay stable if food data or the pantry changes.
- `foods`: search results you've used, so their nutrition and ingredients stay available.
- `preferences.dailyTargets`: your own targets; unset values fall back to generic adult references.

Older data under `baskt` or `eatclean` is migrated automatically (its undated log is filed under the day of migration) and left in place as a backup. Records that fail validation are dropped, and the original data is copied to a `baskt.v2.backup-<timestamp>` key first.

Limitations: data lives only in this browser on this device. There's no login, cross-device sync, or cloud backup, and clearing site data deletes it.
