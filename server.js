/**
 * Legacy baskt Express server (port 3000).
 * The project now uses Baskt FastAPI on port 8000, which serves the UI and all /api routes.
 *
 * To run the unified app:
 *   cd baskt/backend && uvicorn app.main:app --reload --port 8000
 */
console.error(
  "This Node server is deprecated. Use: cd baskt/backend && uvicorn app.main:app --reload --port 8000"
);
process.exit(1);