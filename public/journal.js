// Baskt daily journal: local-date helpers, versioned storage, per-day entries and totals.
// Loaded by index.html as a classic script (window.Journal) and by tests via vm.runInThisContext.
(function (root) {
  'use strict';

  const NUTRIENTS = ['kcal', 'p', 'c', 'f', 'fib', 'fe', 'vc', 'ca'];
  const DEFAULT_TARGETS = { kcal: 2000, p: 60, c: 250, f: 65, fib: 28, fe: 18, vc: 90, ca: 1000 };
  const OZ = 28.3495;
  const UNITS = { serv: { min: 0.25, max: 99, step: 0.25 }, g: { min: 1, max: 5000, step: 10 }, oz: { min: 0.25, max: 200, step: 0.5 } };
  const MEALS = ['breakfast', 'lunch', 'dinner', 'snack'];
  const STORE = 'baskt.v2';
  const LEGACY = ['baskt', 'eatclean'];
  const KEY_RE = /^(\d{4})-(\d{2})-(\d{2})$/;

  const pad = n => String(n).padStart(2, '0');
  const round3 = n => Math.round(n * 1000) / 1000;

  // ---- local calendar dates (never toISOString, which is UTC) ----
  function dateKey(d = new Date()) {
    return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
  }
  // Noon avoids DST gaps, which in some zones fall at local midnight.
  function keyToDate(k) {
    const m = KEY_RE.exec(k);
    return new Date(+m[1], +m[2] - 1, +m[3], 12);
  }
  function isKey(k) {
    return typeof k === 'string' && KEY_RE.test(k) && dateKey(keyToDate(k)) === k;
  }
  function addDays(k, n) {
    const d = keyToDate(k);
    d.setDate(d.getDate() + n);
    return dateKey(d);
  }
  function daysBetween(a, b) {
    const da = keyToDate(a), db = keyToDate(b);
    return Math.round((Date.UTC(db.getFullYear(), db.getMonth(), db.getDate()) - Date.UTC(da.getFullYear(), da.getMonth(), da.getDate())) / 864e5);
  }
  function windowKeys(end, n = 7) {
    const out = [];
    for (let i = n - 1; i >= 0; i--) out.push(addDays(end, -i));
    return out;
  }
  function localIso(d = new Date()) {
    const off = -d.getTimezoneOffset(), a = Math.abs(off);
    return `${dateKey(d)}T${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}${off >= 0 ? '+' : '-'}${pad(Math.floor(a / 60))}:${pad(a % 60)}`;
  }

  // ---- amounts and nutrients ----
  function clampAmount(a, u) {
    const s = UNITS[u] || UNITS.serv;
    if (!Number.isFinite(a)) a = u === 'g' ? 100 : 1;
    a = u === 'g' ? Math.round(a) : Math.round(a * 100) / 100;
    return Math.min(s.max, Math.max(s.min, a));
  }
  const gramsPer = f => (f && f.gs) || 100;
  function servings(f, a, u) {
    return u === 'g' ? a / gramsPer(f) : u === 'oz' ? a * OZ / gramsPer(f) : a;
  }
  function convert(f, a, from, to) {
    if (from === to) return a;
    const g = from === 'g' ? a : from === 'oz' ? a * OZ : a * gramsPer(f);
    return clampAmount(to === 'g' ? g : to === 'oz' ? g / OZ : g / gramsPer(f), to);
  }
  function nutrientsFor(food, quantity, unit) {
    const m = servings(food, quantity, unit), out = {};
    NUTRIENTS.forEach(k => { out[k] = round3((+food[k] || 0) * m); });
    return out;
  }
  function targets(prefs) {
    const values = { ...DEFAULT_TARGETS }, c = (prefs && prefs.dailyTargets) || {};
    let custom = false;
    NUTRIENTS.forEach(k => {
      const v = +c[k];
      if (c[k] != null && Number.isFinite(v) && v > 0) { values[k] = v; if (v !== DEFAULT_TARGETS[k]) custom = true; }
    });
    return { values, custom };
  }

  // ---- entries ----
  let seq = 0;
  function makeId(prefix = 'entry') {
    return `${prefix}-${Date.now().toString(36)}-${(seq++).toString(36)}${Math.random().toString(36).slice(2, 6)}`;
  }
  function emptyDb() {
    return { schemaVersion: 2, pantry: [], dailyLogs: {}, foods: [], preferences: { dailyTargets: {} } };
  }
  function makeEntry(food, quantity, unit, opts = {}) {
    const u = UNITS[unit] ? unit : 'serv';
    const q = clampAmount(+quantity, u);
    const e = {
      id: opts.id || makeId(),
      foodId: food.id,
      name: food.name,
      quantity: q,
      unit: u,
      meal: MEALS.includes(opts.meal) ? opts.meal : null,
      loggedAt: localIso(opts.now || new Date()),
      nutrientsSnapshot: nutrientsFor(food, q, u),
      dataSource: food.src || 'Baskt built-in'
    };
    if (food.ing) e.ingredients = food.ing;
    return e;
  }
  const entriesFor = (db, k) => db.dailyLogs[k] || [];
  const findEntry = (db, k, id) => entriesFor(db, k).find(e => e.id === id) || null;
  function addEntry(db, k, entry) {
    if (!isKey(k)) throw new Error('Invalid date key: ' + k);
    (db.dailyLogs[k] = db.dailyLogs[k] || []).push(entry);
    return entry;
  }
  // With the source food available, nutrients are recalculated; without it, the snapshot is scaled in the same unit.
  function updateEntry(db, k, id, patch, food) {
    const e = findEntry(db, k, id);
    if (!e) return null;
    if (patch.meal !== undefined) e.meal = MEALS.includes(patch.meal) ? patch.meal : null;
    if (patch.quantity !== undefined || patch.unit !== undefined) {
      if (food) {
        const unit = UNITS[patch.unit] ? patch.unit : e.unit;
        let q = patch.quantity !== undefined ? +patch.quantity : convert(food, e.quantity, e.unit, unit);
        q = clampAmount(q, unit);
        e.quantity = q; e.unit = unit; e.nutrientsSnapshot = nutrientsFor(food, q, unit);
      } else if (patch.quantity !== undefined) {
        const q = clampAmount(+patch.quantity, e.unit), r = e.quantity > 0 ? q / e.quantity : 1;
        NUTRIENTS.forEach(n => { e.nutrientsSnapshot[n] = round3((e.nutrientsSnapshot[n] || 0) * r); });
        e.quantity = q;
      }
    }
    return e;
  }
  function removeEntry(db, k, id) {
    const list = db.dailyLogs[k];
    if (!list) return false;
    const i = list.findIndex(e => e.id === id);
    if (i < 0) return false;
    list.splice(i, 1);
    if (!list.length) delete db.dailyLogs[k];
    return true;
  }
  function moveEntry(db, from, to, id) {
    const e = findEntry(db, from, id);
    if (!e || !isKey(to) || from === to) return null;
    removeEntry(db, from, id);
    return addEntry(db, to, e);
  }
  function isDuplicate(list, cand, nowMs, windowMs = 3000) {
    return list.some(e => e.foodId === cand.foodId && e.quantity === cand.quantity && e.unit === cand.unit && e.meal === cand.meal
      && Math.abs(nowMs - Date.parse(e.loggedAt)) < windowMs);
  }

  // ---- aggregation ----
  function totals(list) {
    const t = {};
    NUTRIENTS.forEach(k => { t[k] = 0; });
    (list || []).forEach(e => NUTRIENTS.forEach(k => { t[k] += +(e.nutrientsSnapshot && e.nutrientsSnapshot[k]) || 0; }));
    NUTRIENTS.forEach(k => { t[k] = round3(t[k]); });
    return t;
  }
  function history(db, keys, metric, today) {
    return keys.map(k => {
      const list = entriesFor(db, k), logged = list.length > 0;
      return { key: k, logged, value: logged ? totals(list)[metric] : null, partial: k === today, future: k > today };
    });
  }
  function completedAverage(hist) {
    const done = hist.filter(h => h.logged && !h.partial && !h.future);
    return done.length ? { avg: round3(done.reduce((s, h) => s + h.value, 0) / done.length), days: done.length } : null;
  }

  // ---- storage, validation and migration ----
  function sanitizeEntry(e) {
    if (!e || typeof e !== 'object' || typeof e.foodId !== 'string' || !e.foodId) return null;
    const q = +e.quantity;
    if (!UNITS[e.unit] || !Number.isFinite(q) || q <= 0) return null;
    const s = e.nutrientsSnapshot || {}, snap = {};
    NUTRIENTS.forEach(k => { const v = +s[k]; snap[k] = Number.isFinite(v) && v >= 0 ? v : 0; });
    const out = {
      id: typeof e.id === 'string' && e.id ? e.id : makeId(),
      foodId: e.foodId,
      name: String(e.name || e.foodId),
      quantity: q,
      unit: e.unit,
      meal: MEALS.includes(e.meal) ? e.meal : null,
      loggedAt: typeof e.loggedAt === 'string' ? e.loggedAt : null,
      nutrientsSnapshot: snap,
      dataSource: String(e.dataSource || '')
    };
    if (typeof e.ingredients === 'string' && e.ingredients) out.ingredients = e.ingredients;
    return out;
  }
  const validFood = f => !!f && typeof f === 'object' && typeof f.id === 'string' && !!f.id && typeof f.name === 'string';
  function pantryItem(food) {
    return { id: 'pantry-' + food.id, foodId: food.id, name: food.name };
  }

  function fromV2(raw) {
    const db = emptyDb();
    let dropped = 0;
    if (Array.isArray(raw.foods)) raw.foods.forEach(f => { if (validFood(f)) db.foods.push(f); else dropped++; });
    if (Array.isArray(raw.pantry)) raw.pantry.forEach(p => {
      const id = p && (p.foodId || p.id);
      if (typeof id !== 'string' || !id) { dropped++; return; }
      if (!db.pantry.some(x => x.foodId === id)) db.pantry.push({ id: 'pantry-' + id, foodId: id, name: String(p.name || id) });
    });
    if (raw.dailyLogs && typeof raw.dailyLogs === 'object') {
      for (const [k, list] of Object.entries(raw.dailyLogs)) {
        if (!isKey(k) || !Array.isArray(list)) { dropped++; continue; }
        const ok = [];
        list.forEach(e => { const c = sanitizeEntry(e); if (c) ok.push(c); else dropped++; });
        if (ok.length) db.dailyLogs[k] = ok;
      }
    }
    const t = raw.preferences && raw.preferences.dailyTargets;
    if (t && typeof t === 'object') NUTRIENTS.forEach(k => {
      const v = +t[k];
      if (t[k] != null && Number.isFinite(v) && v > 0) db.preferences.dailyTargets[k] = v;
    });
    return { db, dropped };
  }

  // v1 stored {log:[{id,a,u}|{id,q}], pantry:[foodId], foods:[...]} with no dates; its log is filed under `today`.
  function fromV1(raw, today, lookup) {
    const db = emptyDb();
    if (Array.isArray(raw.foods)) db.foods = raw.foods.filter(validFood);
    const find = id => (lookup && lookup(id)) || db.foods.find(f => f.id === id) || null;
    if (Array.isArray(raw.pantry)) raw.pantry.forEach(id => {
      const f = find(id);
      if (f && !db.pantry.some(p => p.foodId === id)) db.pantry.push(pantryItem(f));
    });
    const entries = (Array.isArray(raw.log) ? raw.log : []).map(e => {
      const f = e && find(e.id);
      if (!f) return null;
      return UNITS[e.u] && e.a != null ? makeEntry(f, +e.a, e.u) : makeEntry(f, +e.q || 1, 'serv');
    }).filter(Boolean);
    if (entries.length) db.dailyLogs[today] = entries;
    return db;
  }

  function backup(storage, text) {
    try { storage.setItem(STORE + '.backup-' + Date.now(), text); } catch (e) { /* storage full or blocked */ }
  }
  function load(storage, today, lookup, seed) {
    let text = null;
    try { text = storage.getItem(STORE); } catch (e) { /* storage blocked */ }
    if (text) {
      let raw = null;
      try { raw = JSON.parse(text); } catch (e) { raw = null; }
      if (raw && typeof raw === 'object' && raw.schemaVersion === 2) {
        const { db, dropped } = fromV2(raw);
        if (dropped) backup(storage, text);
        return { db, source: 'v2', dropped };
      }
      backup(storage, text);
    }
    for (const k of LEGACY) {
      let t = null;
      try { t = storage.getItem(k); } catch (e) { /* storage blocked */ }
      if (!t) continue;
      try {
        const r = JSON.parse(t);
        if (r && typeof r === 'object') return { db: fromV1(r, today, lookup), source: k, dropped: 0 };
      } catch (e) { /* malformed legacy data is left untouched */ }
    }
    const db = emptyDb();
    if (seed) seed(db);
    return { db, source: 'new', dropped: 0 };
  }
  function save(storage, db) {
    try { storage.setItem(STORE, JSON.stringify(db)); return true; } catch (e) { return false; }
  }

  root.Journal = {
    NUTRIENTS, DEFAULT_TARGETS, OZ, UNITS, MEALS, STORE, LEGACY,
    dateKey, keyToDate, isKey, addDays, daysBetween, windowKeys, localIso,
    clampAmount, gramsPer, servings, convert, nutrientsFor, targets,
    makeId, emptyDb, makeEntry, entriesFor, findEntry, addEntry, updateEntry, removeEntry, moveEntry, isDuplicate,
    totals, history, completedAverage,
    sanitizeEntry, pantryItem, fromV2, fromV1, load, save
  };
})(typeof globalThis !== 'undefined' ? globalThis : this);
