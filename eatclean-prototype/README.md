# eatclean

1. Get a Gemini key: https://aistudio.google.com/apikey
2. Get a USDA key: https://fdc.nal.usda.gov/api-key-signup
3. Copy `.env.example` to `.env` and paste both keys in.
4. Run `npm install` then `npm start`, and open http://localhost:3000

Keys stay on the server. The browser only talks to /api/identify, /api/search and /api/workout.
