import express from 'express';

const { GEMINI_API_KEY: G, USDA_API_KEY: U = 'DEMO_KEY', PORT = 3000 } = process.env;
const MODEL = 'gemini-3.8-flash';
const app = express();
app.use(express.json({ limit: '12mb' }));
app.use(express.static('public'));

const wrap = fn => (req, res) => fn(req, res).catch(e => res.status(500).json({ error: e.message }));
const r1 = n => Math.round((+n || 0) * 10) / 10;
const tannin = s => (/coffee|\btea\b|cocoa|chocolate/i.test(s) ? 'tannin' : '');

async function gemini(parts, schema) {
  if (!G) {
    throw new Error('GEMINI_API_KEY is not set on the server');
  }

  const maxAttempts = 3;
  let lastError;

  for (let attempt = 1; attempt <= maxAttempts; attempt++) {
    try {
      const response = await fetch(
        `https://generativelanguage.googleapis.com/v1beta/models/${MODEL}:generateContent`,
        {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            'x-goog-api-key': G
          },
          body: JSON.stringify({
            contents: [{ parts }],
            generationConfig: {
              responseMimeType: 'application/json',
              responseSchema: schema
            }
          }),
          signal: AbortSignal.timeout(15000)
        }
      );

      const result = await response.json();

      if (!response.ok) {
        const message = result.error?.message || 'Gemini request failed';

        if (![429, 500, 502, 503, 504].includes(response.status)) {
          throw new Error(`Gemini API error (${response.status}): ${message}`);
        }

        lastError = new Error(`Gemini API error (${response.status}): ${message}`);
      } else {
        const output = result.candidates?.[0]?.content?.parts?.[0]?.text;

        if (!output) {
          throw new Error('Gemini returned an empty response.');
        }

        try {
          return JSON.parse(output);
        } catch {
          throw new Error('Gemini returned invalid JSON.');
        }
      }
    } catch (error) {
      lastError = error;

      if (
        error.message.startsWith('Gemini API error (') &&
        ![429, 500, 502, 503, 504].some(code =>
          error.message.startsWith(`Gemini API error (${code})`)
        )
      ) {
        throw error;
      }
    }

    if (attempt < maxAttempts) {
      console.log(`Gemini attempt ${attempt} failed. Retrying...`);
      await new Promise(resolve =>
        setTimeout(resolve, attempt * 2000)
      );
    }
  }

  throw new Error(
    `Gemini unavailable after ${maxAttempts} attempts: ${lastError?.message || 'Unknown error'}`
  );
}

// Vision: list the foods visible in a photo
app.post('/api/identify', wrap(async (req, res) => {
  const { image, mime } = req.body;
  if (!image) return res.status(400).json({ error: 'No image received' });
  res.json(await gemini(
    [{ inline_data: { mime_type: mime || 'image/jpeg', data: image } },
     { text: 'List each distinct food or grocery item visible. Use simple searchable names such as "red bell pepper" or "plain greek yogurt". Ignore non-food objects.' }],
    { type: 'OBJECT', required: ['items'], properties: { items: { type: 'ARRAY', items: { type: 'OBJECT', required: ['name'], properties: { name: { type: 'STRING' } } } } } }
  ));
}));

// Structured post-workout meal from type, duration, intensity, and muscle group
app.post('/api/workout-meal', wrap(async (req, res) => {
  const type = String(req.body.type || 'running');
  const durationMinutes = Math.max(5, Math.min(300, Number(req.body.durationMinutes) || 45));
  const intensity = ['low', 'moderate', 'high'].includes(req.body.intensity) ? req.body.intensity : 'moderate';
  const muscleGroup = String(req.body.muscleGroup || 'cardio');
  const pantry = (req.body.pantry || []).slice(0, 40).join(', ') || 'none';

  const schema = {
    type: 'OBJECT',
    required: ['title', 'meal_items', 'macro_focus', 'notes', 'summary', 'disclaimer'],
    properties: {
      title: { type: 'STRING' },
      meal_items: { type: 'ARRAY', items: { type: 'STRING' } },
      pantry_items: { type: 'ARRAY', items: { type: 'STRING' } },
      macro_focus: { type: 'ARRAY', items: { type: 'STRING' } },
      notes: { type: 'ARRAY', items: { type: 'STRING' } },
      summary: { type: 'STRING' },
      disclaimer: { type: 'STRING' }
    }
  };

  const prompt = `Workout type: ${type}. Duration: ${durationMinutes} minutes. Intensity: ${intensity}. Target muscle group: ${muscleGroup}. User pantry: ${pantry}.
Suggest ONE post-workout meal plan (not pre-workout). Tailor macros to intensity and muscle group:
- Strength + legs/back/chest/arms: emphasize protein and carbs for repair.
- HIIT/high intensity: carbs + protein + hydration note.
- Running/cycling/swimming: carbs to refuel; add protein if session >= 60 min.
- Yoga/low: lighter snack.
Use simple whole foods; prefer pantry items when possible. meal_items should be specific portions (e.g. "Greek yogurt (3/4 cup)"). General wellness only—not medical advice.`;

  if (!G) {
    return res.json(ruleBasedPostWorkout({ type, durationMinutes, intensity, muscleGroup, pantry: req.body.pantry || [] }));
  }

  try {
    res.json(await gemini([{ text: prompt }], schema));
  } catch {
    res.json(ruleBasedPostWorkout({ type, durationMinutes, intensity, muscleGroup, pantry: req.body.pantry || [] }));
  }
}));

function ruleBasedPostWorkout({ type, durationMinutes, intensity, muscleGroup, pantry }) {
  const long = durationMinutes >= 60;
  const hi = intensity === 'high';
  const focus = [];
  const notes = [];
  let foods = [];

  if (type === 'strength') {
    focus.push('protein', 'carbs');
    const byMuscle = {
      legs: ['scrambled eggs', 'Greek yogurt', 'lentils', 'banana'],
      chest: ['eggs', 'Greek yogurt', 'oats'],
      back: ['eggs', 'lentils', 'yogurt'],
      arms: ['Greek yogurt', 'eggs', 'almonds'],
      shoulders: ['eggs', 'yogurt', 'oats'],
      core: ['yogurt', 'banana', 'spinach'],
      full_body: ['eggs', 'Greek yogurt', 'oats', 'banana'],
      cardio: ['eggs', 'Greek yogurt', 'oats']
    };
    foods = byMuscle[muscleGroup] || byMuscle.full_body;
    notes.push('After resistance work, pair protein with carbs to support muscle repair.');
  } else if (type === 'hiit') {
    focus.push('carbs', 'protein', 'fluids');
    foods = hi ? ['banana', 'Greek yogurt', 'oats', 'orange'] : ['banana', 'yogurt', 'orange'];
    notes.push('HIIT sessions benefit from quick-digesting carbs plus moderate protein.');
  } else if (['running', 'cycling', 'swimming'].includes(type)) {
    focus.push(long ? 'carbs' : 'carbs', 'protein');
    if (long) focus.push('fluids');
    foods = long ? ['banana', 'oats', 'Greek yogurt', 'orange'] : ['banana', 'yogurt', 'almonds'];
    notes.push('Endurance training: emphasize glycogen replenishment and some protein.');
  } else {
    focus.push('balanced snack', 'fluids');
    foods = ['yogurt', 'banana', 'orange'];
    notes.push('Lower-intensity sessions need a lighter post-workout snack.');
  }

  if (hi) notes.push('Higher intensity—aim to eat within ~60 minutes after finishing.');

  const pantryHits = foods.filter(f => pantry.some(p => p.toLowerCase().includes(f.split(' ')[0].toLowerCase())));

  return {
    title: 'Suggested post-workout plate',
    meal_items: foods.slice(0, 4),
    pantry_items: pantryHits.length ? pantryHits : pantry.slice(0, 3),
    macro_focus: [...new Set(focus)],
    notes,
    summary: `${type} · ${durationMinutes} min · ${intensity} · ${muscleGroup}`,
    disclaimer: 'General wellness suggestion only—not individualized sports nutrition or medical advice.'
  };
}

// USDA FoodData Central (nutrients per 100 g)
const nut = (a, n) => a.find(x => String(x.nutrientNumber) === n)?.value ?? 0;
async function usda(q) {
  const r = await fetch(`https://api.nal.usda.gov/fdc/v1/foods/search?api_key=${U}&query=${encodeURIComponent(q)}&pageSize=5&dataType=Foundation,SR%20Legacy,Branded`);
  if (!r.ok) return [];
  return ((await r.json()).foods || []).map(x => {
    const a = x.foodNutrients || [];
    return { id: 'u' + x.fdcId, name: x.description + (x.brandName ? ` (${x.brandName})` : ''), srv: '100 g',
      kcal: r1(nut(a, '208')), p: r1(nut(a, '203')), c: r1(nut(a, '205')), f: r1(nut(a, '204')), fib: r1(nut(a, '291')),
      fe: r1(nut(a, '303')), vc: r1(nut(a, '401')), ca: r1(nut(a, '301')), ing: x.ingredients || '', tag: tannin(x.description), src: 'USDA' };
  });
}

// Open Food Facts (packaged foods, per 100 g; iron/vitamin C/calcium arrive in grams)
async function off(q) {
  const r = await fetch(`https://world.openfoodfacts.org/cgi/search.pl?search_terms=${encodeURIComponent(q)}&search_simple=1&action=process&json=1&page_size=5&fields=code,product_name,brands,ingredients_text,nutriments`,
    { headers: { 'User-Agent': 'eatclean/1.0 (student project)' } });
  if (!r.ok) return [];
  return ((await r.json()).products || []).filter(x => x.product_name).map(x => {
    const n = x.nutriments || {};
    return { id: 'o' + x.code, name: x.product_name + (x.brands ? ` (${x.brands.split(',')[0]})` : ''), srv: '100 g',
      kcal: r1(n['energy-kcal_100g']), p: r1(n.proteins_100g), c: r1(n.carbohydrates_100g), f: r1(n.fat_100g), fib: r1(n.fiber_100g),
      fe: r1((n.iron_100g || 0) * 1000), vc: r1((n['vitamin-c_100g'] || 0) * 1000), ca: r1((n.calcium_100g || 0) * 1000),
      ing: x.ingredients_text || '', tag: tannin(x.product_name), src: 'Open Food Facts' };
  });
}

app.get('/api/search', wrap(async (req, res) => {
  const q = String(req.query.q || '').trim().slice(0, 80);
  if (!q) return res.json([]);
  const [a, b] = await Promise.all([usda(q).catch(() => []), off(q).catch(() => [])]);
  res.json([...a, ...b]);
}));


// Look up a packaged food using its barcode
app.get('/api/barcode/:code', wrap(async (req, res) => {
  const code = String(req.params.code || '').trim();

  if (!/^\d{8,14}$/.test(code)) {
    return res.status(400).json({
      error: 'Enter a valid barcode containing 8 to 14 digits.'
    });
  }

  const fields = [
    'code',
    'product_name',
    'brands',
    'quantity',
    'serving_size',
    'nutriments',
    'ingredients_text',
    'allergens',
    'allergens_en',
    'image_url',
    'nutriscore_grade',
    'nova_group',
    'last_modified_t',
    'additives_n',
    'additives_tags'
  ].join(',');

  const url = `https://world.openfoodfacts.org/api/v3/product/${encodeURIComponent(code)}?fields=${fields}`;

  const response = await fetch(url, {
    headers: {
      'User-Agent': 'EatClean/1.0'
    },
    signal: AbortSignal.timeout(15000)
  });

  if (response.status === 404) {
    return res.status(404).json({
      error: 'Product not found. Check the barcode and try again.'
    });
  }

  if (!response.ok) {
    throw new Error(`Open Food Facts returned HTTP ${response.status}`);
  }

  const data = await response.json();

  if (!data.product || data.status === 'failure') {
    return res.status(404).json({
      error: 'Product not found in Open Food Facts.'
    });
  }

  res.json(data.product);
}));

app.listen(PORT, () => console.log(`eatclean running at http://localhost:${PORT}`));
