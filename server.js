/**
 * Legacy eatclean Express server (port 3000).
 * The project now uses NutriLens FastAPI on port 8000, which serves the UI and all /api routes.
 *
 * To run the unified app:
 *   cd nutrilens/backend && uvicorn app.main:app --reload --port 8000
 */
console.error(
  "This Node server is deprecated. Use: cd nutrilens/backend && uvicorn app.main:app --reload --port 8000"
);
process.exit(1);