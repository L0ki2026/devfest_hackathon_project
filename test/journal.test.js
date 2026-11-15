import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import vm from 'node:vm';

vm.runInThisContext(readFileSync(new URL('../public/journal.js', import.meta.url), 'utf8'), { filename: 'journal.js' });
const J = globalThis.Journal;

const withTZ = (tz, fn) => {
  const prev = process.env.TZ;
  process.env.TZ = tz;
  try { return fn(); } finally { if (prev === undefined) delete process.env.TZ; else process.env.TZ = prev; }
};

const banana = { id: 'banana', name: 'Banana', srv: '1 medium', gs: 118, kcal: 105, p: 1.3, c: 27, f: 0.4, fib: 3.1, fe: 0.3, vc: 10, ca: 6 };
const chicken = { id: 'u1001', name: 'Chicken breast', srv: '100 g', gs: 100, kcal: 165, p: 31, c: 0, f: 3.6, fib: 0, fe: 1, vc: 0, ca: 15, src: 'USDA' };
const memStorage = (init = {}) => {
  const m = new Map(Object.entries(init));
  return { getItem: k => (m.has(k) ? m.get(k) : null), setItem: (k, v) => m.set(k, String(v)), keys: () => [...m.keys()], map: m };
};

test('dateKey uses the local calendar date, not UTC', () => {
  withTZ('America/Los_Angeles', () => {
    const lateNight = new Date('2026-11-15T07:30:00Z'); // 11:30 PM Nov 14 in Los Angeles
    assert.equal(J.dateKey(lateNight), '2026-11-14');
    assert.equal(lateNight.toISOString().slice(0, 10), '2026-11-15');
  });
  withTZ('Asia/Kolkata', () => {
    assert.equal(J.dateKey(new Date('2026-11-14T20:00:00Z')), '2026-11-15'); // 1:30 AM Nov 15 in India
  });
});

test('addDays and daysBetween are calendar-based across DST transitions', () => {
  withTZ('America/Los_Angeles', () => {
    assert.equal(J.addDays('2026-03-07', 1), '2026-03-08');
    assert.equal(J.addDays('2026-03-08', 1), '2026-03-09'); // spring forward: 23-hour day
    assert.equal(J.addDays('2026-11-01', 1), '2026-11-02'); // fall back: 25-hour day
    assert.equal(J.addDays('2026-11-02', -1), '2026-11-01');
    assert.equal(J.daysBetween('2026-03-01', '2026-03-31'), 30);
    assert.equal(J.daysBetween('2026-10-25', '2026-11-08'), 14);
    // Fixed 24-hour arithmetic gets this wrong: 1 AM on Nov 1 plus 24 h is still Nov 1 locally.
    const oneAm = new Date(2026, 10, 1, 0, 30);
    assert.equal(J.dateKey(new Date(oneAm.getTime() + 864e5)), '2026-11-01');
    assert.equal(J.addDays(J.dateKey(oneAm), 1), '2026-11-02');
  });
  withTZ('America/Sao_Paulo', () => {
    assert.equal(J.addDays('2018-11-03', 1), '2018-11-04'); // DST began at local midnight
  });
});

test('isKey, windowKeys and month/year boundaries', () => {
  assert.ok(J.isKey('2026-02-28'));
  assert.ok(!J.isKey('2026-02-30'));
  assert.ok(!J.isKey('2026-2-3'));
  assert.ok(!J.isKey(undefined));
  assert.equal(J.addDays('2026-12-31', 1), '2027-01-01');
  assert.equal(J.addDays('2028-03-01', -1), '2028-02-29');
  assert.deepEqual(J.windowKeys('2026-11-03', 7), ['2026-10-28', '2026-10-29', '2026-10-30', '2026-10-31', '2026-11-01', '2026-11-02', '2026-11-03']);
});

test('localIso includes the local UTC offset', () => {
  withTZ('America/Los_Angeles', () => {
    assert.equal(J.localIso(new Date('2026-11-14T16:15:00Z')), '2026-11-14T08:15:00-08:00');
  });
});

test('nutrients scale with amount and unit', () => {
  const g100 = J.makeEntry(chicken, 100, 'g'), g200 = J.makeEntry(chicken, 200, 'g');
  assert.equal(g100.nutrientsSnapshot.kcal, 165);
  assert.equal(g200.nutrientsSnapshot.kcal, 330);
  assert.equal(g200.nutrientsSnapshot.p, 62);
  const oz = J.makeEntry(chicken, 1, 'oz');
  assert.equal(oz.nutrientsSnapshot.kcal, Math.round(165 * J.OZ / 100 * 1000) / 1000);
  assert.equal(J.makeEntry(banana, 2, 'serv').nutrientsSnapshot.kcal, 210);
  assert.equal(J.makeEntry(banana, 118, 'g').nutrientsSnapshot.kcal, 105);
});

test('two dated logs keep independent totals', () => {
  const db = J.emptyDb();
  J.addEntry(db, '2026-11-14', J.makeEntry(banana, 1, 'serv'));
  J.addEntry(db, '2026-11-15', J.makeEntry(chicken, 200, 'g'));
  J.addEntry(db, '2026-11-15', J.makeEntry(banana, 1, 'serv'));
  assert.equal(J.totals(J.entriesFor(db, '2026-11-14')).kcal, 105);
  assert.equal(J.totals(J.entriesFor(db, '2026-11-15')).kcal, 435);
  assert.equal(J.entriesFor(db, '2026-11-13').length, 0);
  assert.throws(() => J.addEntry(db, '2026-13-01', J.makeEntry(banana, 1, 'serv')));
});

test('editing yesterday changes yesterday only; editing recalculates', () => {
  const db = J.emptyDb();
  const y = J.addEntry(db, '2026-11-14', J.makeEntry(banana, 1, 'serv', { meal: 'breakfast' }));
  J.addEntry(db, '2026-11-15', J.makeEntry(banana, 1, 'serv'));
  J.updateEntry(db, '2026-11-14', y.id, { quantity: 2 }, banana);
  assert.equal(J.totals(J.entriesFor(db, '2026-11-14')).kcal, 210);
  assert.equal(J.totals(J.entriesFor(db, '2026-11-15')).kcal, 105);
  J.updateEntry(db, '2026-11-14', y.id, { unit: 'g' }, banana); // unit change keeps the same amount of food
  assert.equal(y.quantity, 236);
  assert.equal(y.nutrientsSnapshot.kcal, 210);
  J.updateEntry(db, '2026-11-14', y.id, { meal: 'lunch' });
  assert.equal(y.meal, 'lunch');
  J.updateEntry(db, '2026-11-14', y.id, { meal: 'brunch' });
  assert.equal(y.meal, null);
});

test('without the source food, edits scale the stored snapshot', () => {
  const db = J.emptyDb();
  const e = J.addEntry(db, '2026-11-15', J.makeEntry(chicken, 100, 'g'));
  J.updateEntry(db, '2026-11-15', e.id, { quantity: 150 }, null);
  assert.equal(e.nutrientsSnapshot.kcal, 247.5);
  J.updateEntry(db, '2026-11-15', e.id, { unit: 'oz' }, null);
  assert.equal(e.unit, 'g');
});

test('remove and move entries', () => {
  const db = J.emptyDb();
  const a = J.addEntry(db, '2026-11-15', J.makeEntry(banana, 1, 'serv'));
  const b = J.addEntry(db, '2026-11-15', J.makeEntry(chicken, 100, 'g'));
  assert.ok(J.moveEntry(db, '2026-11-15', '2026-11-14', b.id));
  assert.equal(J.totals(J.entriesFor(db, '2026-11-14')).kcal, 165);
  assert.equal(J.totals(J.entriesFor(db, '2026-11-15')).kcal, 105);
  assert.ok(J.removeEntry(db, '2026-11-15', a.id));
  assert.equal('2026-11-15' in db.dailyLogs, false);
  assert.equal(J.removeEntry(db, '2026-11-15', a.id), false);
});

test('duplicate submissions are detected within a short window', () => {
  const now = new Date('2026-11-15T16:00:00Z');
  const e = J.makeEntry(banana, 1, 'serv', { now, meal: 'snack' });
  const same = J.makeEntry(banana, 1, 'serv', { meal: 'snack' });
  assert.ok(J.isDuplicate([e], same, now.getTime() + 1000));
  assert.ok(!J.isDuplicate([e], same, now.getTime() + 10000));
  assert.ok(!J.isDuplicate([e], J.makeEntry(banana, 2, 'serv', { meal: 'snack' }), now.getTime() + 1000));
});

test('history separates unlogged days from logged days and marks today partial', () => {
  const db = J.emptyDb();
  J.addEntry(db, '2026-11-12', J.makeEntry(banana, 2, 'serv'));
  J.addEntry(db, '2026-11-14', J.makeEntry(chicken, 100, 'g'));
  J.addEntry(db, '2026-11-15', J.makeEntry(banana, 1, 'serv'));
  const h = J.history(db, J.windowKeys('2026-11-15', 7), 'kcal', '2026-11-15');
  assert.deepEqual(h.map(x => x.value), [null, null, null, 210, null, 165, 105]);
  assert.deepEqual(h.map(x => x.logged), [false, false, false, true, false, true, true]);
  assert.equal(h[6].partial, true);
  assert.deepEqual(J.completedAverage(h), { avg: 187.5, days: 2 });
  assert.equal(J.completedAverage(J.history(db, ['2026-11-15'], 'kcal', '2026-11-15')), null);
});

test('targets merge user values over generic references', () => {
  assert.deepEqual(J.targets(undefined), { values: J.DEFAULT_TARGETS, custom: false });
  const t = J.targets({ dailyTargets: { kcal: 1800, p: null, fib: -3, ca: 'x' } });
  assert.equal(t.values.kcal, 1800);
  assert.equal(t.values.p, 60);
  assert.equal(t.values.fib, 28);
  assert.equal(t.custom, true);
});

test('migrates the undated v1 log to today and keeps the legacy key', () => {
  const v1 = { log: [{ id: 'banana', a: 2, u: 'serv' }, { id: 'oats', q: 1 }, { id: 'u1001', a: 150, u: 'g' }, { id: 'ghost', a: 1, u: 'serv' }], pantry: ['banana', 'ghost'], foods: [chicken] };
  const st = memStorage({ baskt: JSON.stringify(v1) });
  const lookup = id => ({ banana, oats: { id: 'oats', name: 'Rolled oats', gs: 40, kcal: 150 } })[id];
  const { db, source } = J.load(st, '2026-11-15', lookup);
  assert.equal(source, 'baskt');
  const today = J.entriesFor(db, '2026-11-15');
  assert.deepEqual(today.map(e => [e.foodId, e.quantity, e.unit]), [['banana', 2, 'serv'], ['oats', 1, 'serv'], ['u1001', 150, 'g']]);
  assert.equal(J.totals(today).kcal, 210 + 150 + 247.5);
  assert.deepEqual(db.pantry, [{ id: 'pantry-banana', foodId: 'banana', name: 'Banana' }]);
  assert.equal(today[2].dataSource, 'USDA');
  assert.ok(st.getItem('baskt'), 'legacy data is not deleted');
});

test('falls back to the eatclean key and seeds new users', () => {
  const st = memStorage({ eatclean: JSON.stringify({ log: [{ id: 'banana', q: 1 }] }) });
  assert.equal(J.load(st, '2026-11-15', id => (id === 'banana' ? banana : null)).source, 'eatclean');
  const fresh = J.load(memStorage(), '2026-11-15', null, db => db.pantry.push(J.pantryItem(banana)));
  assert.equal(fresh.source, 'new');
  assert.deepEqual(fresh.db.dailyLogs, {});
  assert.equal(fresh.db.pantry.length, 1);
});

test('v2 round-trips, and malformed records are dropped with a backup', () => {
  const db = J.emptyDb();
  db.pantry.push(J.pantryItem(banana));
  J.addEntry(db, '2026-11-14', J.makeEntry(banana, 1, 'serv', { meal: 'snack' }));
  const st = memStorage();
  assert.ok(J.save(st, db));
  const again = J.load(st, '2026-11-15');
  assert.equal(again.source, 'v2');
  assert.deepEqual(again.db, db);

  const bad = JSON.parse(st.getItem(J.STORE));
  bad.dailyLogs['2026-11-14'].push({ foodId: 'banana', quantity: -1, unit: 'serv' }, null);
  bad.dailyLogs['not-a-date'] = [];
  st.setItem(J.STORE, JSON.stringify(bad));
  const fixed = J.load(st, '2026-11-15');
  assert.equal(fixed.dropped, 3);
  assert.equal(J.entriesFor(fixed.db, '2026-11-14').length, 1);
  assert.ok(st.keys().some(k => k.startsWith(J.STORE + '.backup-')));
});

test('corrupt v2 JSON is backed up and legacy data is used instead', () => {
  const st = memStorage({ [J.STORE]: '{not json', baskt: JSON.stringify({ log: [{ id: 'banana', a: 1, u: 'serv' }] }) });
  const r = J.load(st, '2026-11-15', id => (id === 'banana' ? banana : null));
  assert.equal(r.source, 'baskt');
  assert.equal(J.entriesFor(r.db, '2026-11-15').length, 1);
  assert.ok(st.keys().some(k => k.startsWith(J.STORE + '.backup-') && st.getItem(k) === '{not json'));
});

test('removing a pantry item does not touch logs, and vice versa', () => {
  const db = J.emptyDb();
  db.pantry.push(J.pantryItem(banana));
  const e = J.addEntry(db, '2026-11-14', J.makeEntry(banana, 1, 'serv'));
  db.pantry = db.pantry.filter(p => p.foodId !== 'banana');
  assert.equal(J.entriesFor(db, '2026-11-14').length, 1);
  db.pantry.push(J.pantryItem(banana));
  J.removeEntry(db, '2026-11-14', e.id);
  assert.equal(db.pantry.length, 1);
});
