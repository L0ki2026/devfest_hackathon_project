import express from 'express';

const { GEMINI_API_KEY: G, USDA_API_KEY: U = 'DEMO_KEY', PORT = 3000 } = process.env;
const MODEL = 'gemini-2.5-flash';
const app = express();
app.use(express.json({ limit: '12mb' }));
app.use(express.static('public'));

const wrap = fn => (req, res) => fn(req, res).catch(e => res.status(500).json({ error: e.message }));
const r1 = n => Math.round((+n || 0) * 10) / 10;
const tannin = s => (/coffee|\btea\b|cocoa|chocolate/i.test(s) ? 'tannin' : '');

async function gemini(parts, schema) {
  if (!G) throw new Error('GEMINI_API_KEY is not set on the server');
  const r = await fetch(`https://generativelanguage.googleapis.com/v1beta/models/${MODEL}:generateContent`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', 'x-goog-api-key': G },
    body: JSON.stringify({
      contents: [{ parts }],
      generationConfig: { responseMimeType: 'application/json', responseSchema: schema }
    })
  });
  const j = await r.json();
  if (!r.ok) throw new Error(j.error?.message || 'Gemini request failed');
  return JSON.parse(j.candidates[0].content.parts[0].text);
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

// Argument extraction: free-text workout -> structured fuel suggestions
app.post('/api/workout', wrap(async (req, res) => {
  const text = String(req.body.text || '').slice(0, 300);
  const pantry = (req.body.pantry || []).slice(0, 40).join(', ') || 'none';
  res.json(await gemini(
    [{ text: `Workout description: "${text}". Pantry: ${pantry}. Return the workout kind (strength, endurance, or light), minutes (0 if not stated), and 2-3 whole-food suggestions each for before and after the workout. Prefer pantry items. Use short food names. General guidance only.` }],
    { type: 'OBJECT', required: ['kind', 'min', 'pre', 'post'], properties: { kind: { type: 'STRING' }, min: { type: 'INTEGER' }, pre: { type: 'ARRAY', items: { type: 'STRING' } }, post: { type: 'ARRAY', items: { type: 'STRING' } } } }
  ));
}));

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

app.listen(PORT, () => console.log(`eatclean running at http://localhost:${PORT}`));
