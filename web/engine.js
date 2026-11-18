/* battlesim engine, JavaScript port of battlesim.py (same model, same scenario format). */
const SIDE_DEFAULTS = {
  strength: 100, quality: 1, training: 1, training_cap: 1, learning: 0, morale: 0.8,
  morale_sensitivity: 1, morale_floor: 0.15, logistics: 0.8, supply_range: 5, air: 50, naval: 0,
  c2: 1, reserves: 0, mobilization_delay: 0, mobilization_rate: 0.1, replacement: 0,
  terrain_defense: 1, depth: 5, break_point: 0.6, posture: "defend", tempo: 1,
  // supplies & economy (only used when the scenario has "resources": true)
  water_self: 1, water_stock: 60, food_self: 1, food_stock: 60, fuel_self: 1, fuel_stock: 60,
  trade_dep: 100, econ_tol: 15, blockade: 0.6, water_cut: 0,
  // forces stationed far away (e.g. East Malaysia) that must cross the sea to join
  remote_share: 0, remote_delay: 5, remote_rate: 0.1, remote_name: "",
  // special operations: chance each is attempted
  op_raid: 0, op_airborne: 0, op_amphib: 0, op_sabotage: 0,
  // manoeuvre: how hard a side shifts weight to its breakthroughs to form pincers, and how readily it pulls back out of a forming pocket
  pincer: 0, retreat: 0.5,
  // sealed pockets: how hard this side storms pockets it has surrounded (vs starving them out), and how readily its own trapped troops try to break out
  siege: 0.4, breakout: 0.5,
};
const GLOBAL_DEFAULTS = {
  max_turns: 52, lethality: 0.03, advance_rate: 0.5, air_weight: 0.3, naval_weight: 0, noise: 0.25,
  morale_rate: 1,
  cohesion: 0,      // if > 0: the furthest a sector's front can run ahead of its neighbours (distance units); thrusts wait for their flanks
  stall: 0,         // defence dominance: log force ratio a side must exceed before the front moves at all   // scales how fast combat losses and lost ground erode morale
};

function makeRng(seed) {
  let a = seed >>> 0;
  const u = () => {
    a = (a + 0x6D2B79F5) >>> 0;
    let t = a;
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
  let spare = null;
  const normal = () => {
    if (spare !== null) { const s = spare; spare = null; return s; }
    let x, y, r;
    do { x = 2 * u() - 1; y = 2 * u() - 1; r = x * x + y * y; } while (r >= 1 || r === 0);
    const f = Math.sqrt(-2 * Math.log(r) / r);
    spare = y * f;
    return x * f;
  };
  return {
    random: u,
    uniform: (lo, hi) => lo + (hi - lo) * u(),
    triangular: (lo, mode, hi) => {
      const x = u(), c = (mode - lo) / (hi - lo);
      return x < c ? lo + Math.sqrt(x * (hi - lo) * (mode - lo)) : hi - Math.sqrt((1 - x) * (hi - lo) * (hi - mode));
    },
    lognormal: (sig) => Math.exp(sig * normal()),
  };
}

function sampleSpec(spec, rng) {
  if (typeof spec === "number") return spec;
  if (Array.isArray(spec)) {
    if (spec.length === 2) return rng.uniform(spec[0], spec[1]);
    if (spec.length === 3) {
      const [lo, mode, hi] = spec;
      if (lo === hi) return lo;
      return rng.triangular(lo, Math.min(Math.max(mode, lo), hi), hi);
    }
  }
  return spec;
}
const isUncertain = (s) => Array.isArray(s) && s.length >= 2 && Math.min(...s) !== Math.max(...s);

function simulateOnce(sc, rng) {
  const g = { ...GLOBAL_DEFAULTS };
  const sampled = {};
  for (const [k, v] of Object.entries(sc.globals)) {
    if (typeof v === "string") { g[k] = v; continue; }
    g[k] = sampleSpec(v, rng);
    if (isUncertain(v)) sampled["globals." + k] = g[k];
  }
  const sides = {};
  for (const key of ["A", "B"]) {
    const p = { ...SIDE_DEFAULTS };
    for (const [k, v] of Object.entries(sc.sides[key])) {
      if (k === "name") continue;
      p[k] = typeof v === "string" ? v : sampleSpec(v, rng);
      if (isUncertain(v)) sampled[key + "." + k] = p[k];
    }
    sides[key] = p;
  }
  const fired = [], mods = [];
  let ceasefire = null;
  for (const ev of sc.events) {
    const hit = rng.random() < sampleSpec(ev.prob ?? 0.5, rng);
    sampled["event:" + ev.name] = hit ? 1 : 0;
    const effects = hit ? (ev.effects || []) : (ev.else_effects || []);
    if (hit) fired.push(ev.name);
    if (hit && ev.ceasefire_turn !== undefined) {
      const ct = Math.round(sampleSpec(ev.ceasefire_turn, rng));
      ceasefire = ceasefire === null ? ct : Math.min(ceasefire, ct);
    }
    for (const e of effects) {
      mods.push([e.side, e.param, sampleSpec(e.mult ?? 1, rng), sampleSpec(e.add ?? 0, rng),
        e.from_turn ?? 0, e.to_turn ?? 1e9]);
    }
  }
  // mods indexed by side+param so each lookup only scans its own few entries
  let idxN = -1, idx = {};
  const P = (side, name, t) => {
    if (mods.length !== idxN) {
      idxN = mods.length; idx = { A: {}, B: {} };
      for (const m of mods) { const ks = m[0] === "both" ? ["A", "B"] : m[0] === "A" || m[0] === "B" ? [m[0]] : []; for (const k of ks) (idx[k][m[1]] ||= []).push(m); }
    }
    let v = sides[side][name];
    if (typeof v === "string") return v;
    const list = idx[side][name];
    if (list) for (const [, , m, a, f0, f1] of list) if (f0 <= t && t <= f1) v = v * m + a;
    return v;
  };
  const G = (name, t) => {
    let v = g[name];
    for (const [s, n, m, a, f0, f1] of mods) if (s === "globals" && n === name && f0 <= t && t <= f1) v = v * m + a;
    return v;
  };

  const NAME = { A: sc.sides.A.name || "A", B: sc.sides.B.name || "B" };
  const other = (k) => (k === "A" ? "B" : "A");
  const notes = [];   // [day, side, text] for the replay log
  const sectors = sc.sectors || [{ name: "Front", weight: 1, relA: 1, relB: 1, crossing: 1 }];
  const nS = sectors.length;
  const fS = new Array(nS).fill(0);
  // local conditions differ by sector (commanders, ground, how well each side guessed where the blow would fall)
  const luck = sectors.map(() => (sc.sectors ? 0.4 * (2 * rng.random() - 1) : 0));
  const wsum = sectors.reduce((a, x) => a + x.weight, 0);
  const W = sectors.map((x) => x.weight / wsum);
  const useRes = !!sc.resources;

  // special operations: decide up front which are attempted, when, where, and whether they succeed
  const ops = [];
  const OPS = [["op_raid", "raid", "special forces raid"], ["op_airborne", "airborne", "airborne landing"], ["op_amphib", "amphib", "amphibious landing"], ["op_sabotage", "sabotage", "sabotage of water and fuel"]];
  for (const k of ["A", "B"]) {
    for (const [param, kind, label] of OPS) {
      const pr = sides[k][param];
      if (!pr) continue;
      const hit = rng.random() < pr;
      sampled[`event:${NAME[k]} ${label}`] = hit ? 1 : 0;
      if (!hit) continue;
      const op = { side: k, kind, ok: true };
      if (kind === "raid") { op.day = 1 + Math.floor(rng.random() * 3); op.ok = rng.random() < 0.7; }
      if (kind === "sabotage") { op.day = 1 + Math.floor(rng.random() * 5); op.ok = rng.random() < 0.65; }
      if (kind === "airborne") { op.day = 2 + Math.floor(rng.random() * 7); op.sector = Math.floor(rng.random() * nS); op.jump = 1 + rng.random(); op.ok = rng.random() < 0.75; op.force = 0.03; }
      if (kind === "amphib") {
        op.day = 3 + Math.floor(rng.random() * 10);
        const flanks = sectors.map((x, i) => [x.crossing, i]).sort((a, b) => a[0] - b[0]).slice(0, 2).map((x) => x[1]);
        op.sector = flanks[Math.floor(rng.random() * flanks.length)];
        op.jump = 1.5 + 1.5 * rng.random(); op.force = 0.05; op.navRoll = rng.random();
      }
      ops.push(op);
    }
  }
  for (const op of ops) {
    if (op.kind === "raid" && op.ok) {
      const e = other(op.side);
      mods.push([e, "c2", 0.8, 0, op.day, op.day + 4], [e, "air", 0.85, 0, op.day, op.day + 4]);
    }
  }
  const stock = {}, econ = { A: 0, B: 0 }, drain = {}, flags = {};
  for (const k of ["A", "B"]) {
    stock[k] = { water: P(k, "water_stock", 0), food: P(k, "food_stock", 0), fuel: P(k, "fuel_stock", 0) };
    drain[k] = { combat: 0, ground: 0, water: 0, food: 0, fuel: 0, econ: 0, ops: 0 };
  }
  const fuelPenalty = { A: 1, B: 1 };
  const landings = [];
  const pocket = {}, pocketWarned = {}, escapeNoted = {}, counterNoted = {}, pocketsClosed = [], trPocket = [[]], held = [], trHeld = [[]];
  let heldId = 0;
  const remote = {}, remoteLost = { A: 0, B: 0 }, remoteArrived = { A: 0, B: 0 };

  const S = { A: P("A", "strength", 0), B: P("B", "strength", 0) };
  for (const k of ["A", "B"]) { const sh = P(k, "remote_share", 0); remote[k] = S[k] * sh; S[k] -= remote[k]; }
  const peak = { ...S };
  const morale = { A: P("A", "morale", 0), B: P("B", "morale", 0) };
  const training = { A: P("A", "training", 0), B: P("B", "training", 0) };
  const reserves = { A: P("A", "reserves", 0), B: P("B", "reserves", 0) };
  const loss = { A: 0, B: 0 };
  let front = 0;
  let maxTurns = Math.trunc(G("max_turns", 0));
  if (ceasefire !== null) maxTurns = Math.min(maxTurns, ceasefire);
  const trF = [0], trA = [S.A], trB = [S.B], trMA = [morale.A], trMB = [morale.B], trLA = [0], trLB = [0];
  const trU = [{ A: W.map((w) => w * S.A), B: W.map((w) => w * S.B) }];
  let curAlloc = { A: W.slice(), B: W.slice() };
  const trS = [fS.slice()], trRes = [{ A: { ...stock.A, econ: 0 }, B: { ...stock.B, econ: 0 } }];
  let outcome = "stalemate", reason = "turn limit", t = 0;
  if (ceasefire !== null && ceasefire <= G("max_turns", 0)) reason = "ceasefire imposed";

  for (t = 1; t <= maxTurns; t++) {
    const airA = Math.max(P("A", "air", t), 0.01), airB = Math.max(P("B", "air", t), 0.01);
    const airShare = airA ** 1.5 / (airA ** 1.5 + airB ** 1.5);
    const navA = Math.max(P("A", "naval", t), 0.01), navB = Math.max(P("B", "naval", t), 0.01);
    const navShare = navA ** 1.5 / (navA ** 1.5 + navB ** 1.5);
    const aw = G("air_weight", t), nw = G("naval_weight", t);
    const airM = { A: 1 + aw * (2 * airShare - 1), B: 1 + aw * (1 - 2 * airShare) };
    const navM = { A: 1 + nw * (2 * navShare - 1), B: 1 + nw * (1 - 2 * navShare) };
    const E = {};
    const sea = { A: navShare, B: 1 - navShare };
    for (const [k, sign] of [["A", 1], ["B", -1]]) {
      const depthIn = Math.max(0, sign * front);
      let supply = P(k, "logistics", t) / (1 + depthIn / Math.max(P(k, "supply_range", t), 0.1));
      supply *= (0.5 + 0.5 * navM[k]) * fuelPenalty[k];
      const moraleEff = 0.4 + 0.6 * morale[k];
      training[k] = Math.min(training[k] + P(k, "learning", t), Math.max(P(k, "training_cap", t), sides[k].training));
      E[k] = S[k] * P(k, "quality", t) * training[k] * moraleEff * supply * airM[k] * navM[k] * P(k, "c2", t);
    }
    // troops holding the ring round a sealed pocket are not available on the main front
    for (const k of ["A", "B"]) {
      const tied = held.filter((h) => !h.end && h.side !== k).reduce((a, h) => a + h.troops * (0.45 + 0.4 * P(k, "siege", t)), 0);
      if (tied > 0) E[k] *= 1 - Math.min(0.45, tied / Math.max(1, S[k]));
    }
    // forces from far away (East Malaysia) cross the sea; the enemy's sea and air control sinks some
    for (const k of ["A", "B"]) {
      if (remote[k] > 0.01 && t > P(k, "remote_delay", t)) {
        const send = remote[k] * P(k, "remote_rate", t);
        remote[k] -= send;
        const through = send * (0.7 + 0.3 * Math.sqrt(sea[k] * (k === "A" ? airShare : 1 - airShare)));
        S[k] += through; remoteArrived[k] += through; remoteLost[k] += send - through;
        if (!flags[k + "remote"]) { flags[k + "remote"] = 1; notes.push([t, k, `${NAME[k]}'s divisions from ${sides[k].remote_name || "afar"} begin arriving by sea and air.`]); }
        if (remote[k] < 0.05 * (remoteArrived[k] + remoteLost[k] + remote[k]) && !flags[k + "remote2"]) {
          flags[k + "remote2"] = 1;
          const lostPct = Math.round(100 * remoteLost[k] / (remoteArrived[k] + remoteLost[k]));
          notes.push([t, lostPct > 25 ? other(k) : k, `Most of the ${sides[k].remote_name || "remote"} forces have crossed. About ${lostPct}% were lost to ${NAME[other(k)]}'s navy and air force on the way.`]);
        }
      }
    }
    // special operations that land on this day
    for (const op of ops) {
      if (op.day !== t) continue;
      const k = op.side, e = other(k), dir = k === "A" ? 1 : -1;
      if (op.kind === "raid") notes.push([t, op.ok ? k : e, op.ok ? `${NAME[k]} special forces raid ${NAME[e]}'s command posts and air defences.` : `A ${NAME[k]} special forces raid is detected and fails.`]);
      if (op.kind === "sabotage") {
        if (op.ok) { stock[e].water *= 0.7; stock[e].fuel *= 0.6; notes.push([t, k, `Saboteurs hit ${NAME[e]}'s water works and fuel depots.`]); }
        else notes.push([t, e, `A ${NAME[k]} sabotage team is caught before it reaches ${NAME[e]}'s water and fuel sites.`]);
      }
      if (op.kind === "airborne" || op.kind === "amphib") {
        const ok = op.kind === "amphib" ? op.navRoll < 0.3 + 0.6 * sea[k] : op.ok;
        const force = S[k] * op.force, i = op.sector, label = op.kind === "airborne" ? "airborne landing" : "amphibious landing";
        S[k] -= force;
        if (ok) {
          const target = fS[i] + dir * op.jump;
          fS[i] = target;
          morale[e] -= 0.06; drain[e].ops += 0.06;
          landings.push({ side: k, kind: op.kind, sector: i, day: t, f: target, until: t + 4, fate: null, force });
          notes.push([t, k, `${NAME[k]} ${label} in the ${sectors[i].name} sector, ${Math.round(op.jump * 10)} km ahead of the front.`]);
        } else {
          S[k] += force * 0.4;
          morale[k] -= 0.03; drain[k].ops += 0.03;
          landings.push({ side: k, kind: op.kind, sector: i, day: t, f: fS[i] + dir * op.jump, until: t, fate: "failed", end: t, force });
          notes.push([t, e, `A ${NAME[k]} ${label} in the ${sectors[i].name} sector is broken up before it lands. Most of the force is lost.`]);
        }
      }
    }
    // each sector: forces split by sector weight, terrain helps whoever defends on home soil, crossing water hurts the attacker
    const sig = G("noise", t), leth = G("lethality", t);
    let infA = 0, infB = 0;
    // pincer doctrine: each side feeds reserves to the sectors where it is already ahead, so breakthroughs widen into pincers
    const alloc = {};
    for (const [k, dir] of [["A", 1], ["B", -1]]) {
      const pin = P(k, "pincer", t);
      const mean = fS.reduce((a, f, i) => a + dir * f * W[i], 0);
      const raw = W.map((w, i) => w * Math.max(0.3, 1 + pin * Math.max(-0.7, Math.min(1.5, (dir * fS[i] - mean) * 0.8))));
      const tot = raw.reduce((a, b) => a + b, 0);
      alloc[k] = raw.map((x) => x / tot);
    }
    curAlloc = alloc;
    for (let i = 0; i < nS; i++) {
      const sx = sectors[i], f = fS[i];
      const homeA = f < 0 || (f === 0 && sides.A.posture === "defend");
      const homeB = f > 0 || (f === 0 && sides.B.posture === "defend");
      let eA = E.A * alloc.A[i] * (homeA ? 1 + (P("A", "terrain_defense", t) - 1) * sx.relA : 1);
      let eB = E.B * alloc.B[i] * (homeB ? 1 + (P("B", "terrain_defense", t) - 1) * sx.relB : 1);
      if (Math.abs(f) < 0.3) { if (eA > eB) eA *= sx.crossing; else eB *= sx.crossing; }
      infA += eA; infB += eB;
      const lr = Math.log(Math.max(eA, 1e-6) / Math.max(eB, 1e-6)) + luck[i];
      const push = Math.sign(lr) * Math.tanh(1.2 * Math.max(0, Math.abs(lr) - G("stall", t)));
      fS[i] += G("advance_rate", t) * push * rng.lognormal(sig) * P(push >= 0 ? "A" : "B", "tempo", t) * (sx.mobility ?? 1);
    }
    // flank cohesion: a thrust far ahead of its neighbours has open flanks and stalls, and the line beside it is levered back
    const coh = G("cohesion", t);
    if (coh > 0) for (let pass = 0; pass < 2; pass++) for (let i = 0; i < nS - 1; i++) {
      const gap = fS[i] - fS[i + 1], over = Math.abs(gap) - coh;
      if (over > 0) { const s = Math.sign(gap) * over / 2; fS[i] -= s; fS[i + 1] += s; }
    }
    const lA = Math.min(S.A, leth * infB * rng.lognormal(sig));
    const lB = Math.min(S.B, leth * infA * rng.lognormal(sig));
    // encirclement: a sector whose neighbours have been pushed well past it becomes a pocket.
    // The defender there pulls back (gives up ground, saves troops), holds and hopes to break out, or is trapped when the pincers close.
    const pocketsToday = [];
    for (const [k, dir] of [["A", -1], ["B", 1]]) {          // k = defender; enemy advance into k's side is dir * f
      const e = other(k);
      for (let i = 1; i < nS - 1; i++) {
        const adv = dir * fS[i], shoulders = Math.min(dir * fS[i - 1], dir * fS[i + 1]);
        const exposure = shoulders - adv;
        const key = k + i;
        if (exposure < 0.8 || shoulders < 0.3) { if (pocket[key]) pocket[key] = Math.max(0, pocket[key] - 0.2); continue; }
        if (!pocketWarned[key]) { pocketWarned[key] = 1; notes.push([t, e, `A pocket is forming around ${NAME[k]}'s troops in the ${sectors[i].name} sector: the front has been pushed back on both sides of it.`]); }
        if (rng.random() < P(k, "retreat", t) * 0.6) {
          // escape: fall back toward the shoulders
          const back = 0.5 * exposure;
          fS[i] += dir * back;
          morale[k] -= 0.006; drain[k].ground += 0.006;
          pocket[key] = Math.max(0, (pocket[key] || 0) - 0.35);
          if (!escapeNoted[key] || t - escapeNoted[key] > 10) { escapeNoted[key] = t; notes.push([t, k, `${NAME[k]}'s troops in the ${sectors[i].name} sector pull back ${Math.round(back * 10)} km to escape the closing pincers.`]); }
        } else {
          // hold: the pincers tighten unless the defender is locally stronger and counter-attacks a shoulder
          const local = (k === "A" ? E.A * alloc.A[i] : E.B * alloc.B[i]) / Math.max(1e-6, k === "A" ? E.B * alloc.B[i] : E.A * alloc.A[i]);
          if (local > 1.1 && rng.random() < 0.5) {
            const j = dir * fS[i - 1] > dir * fS[i + 1] ? i - 1 : i + 1;
            fS[j] -= dir * 0.15 * Math.min(2, local);
            pocket[key] = Math.max(0, (pocket[key] || 0) - 0.15);
            if (!counterNoted[key] || t - counterNoted[key] > 10) { counterNoted[key] = t; notes.push([t, k, `${NAME[k]} counter-attacks into the flank of the ${sectors[j].name} sector to stop the encirclement.`]); }
          } else {
            pocket[key] = (pocket[key] || 0) + 0.12 + 0.1 * (exposure - 0.8);
          }
        }
        pocketsToday.push([k, i, Math.min(1, pocket[key] || 0)]);
        if ((pocket[key] || 0) >= 1) {
          // the ring closes: the troops inside are cut off from the main front but still fighting
          const trapped = S[k] * alloc[k][i] * (0.5 + 0.3 * rng.random());
          S[k] -= trapped;
          const hit = 0.03 + 0.25 * trapped / Math.max(1, S[k] + trapped);
          morale[k] -= hit; drain[k].combat += hit;
          morale[e] = Math.min(1, morale[e] + 0.02);
          held.push({ id: heldId++, side: k, sector: i, f: fS[i], troops: trapped, start: trapped, supply: 7 + 16 * rng.random(), pm: Math.min(1, morale[k] + 0.1), day: t });
          fS[i] = dir * shoulders;   // the main front closes up behind the pocket
          pocket[key] = 0; pocketWarned[key] = 0;
          pocketsClosed.push({ side: k, sector: i, day: t, trapped });
          notes.push([t, e, `The pincers close in the ${sectors[i].name} sector. About ${(trapped).toFixed(1)}k of ${NAME[k]}'s troops are cut off. They will dig in and wait for relief, try to break out, or surrender.`]);
        }
      }
    }
    trPocket.push(pocketsToday);
    // sealed pockets: supplies run down; the encircler storms or starves them; the trapped troops wait for relief, break out, or give up
    for (const h of held) {
      if (h.end) continue;
      const k = h.side, e = other(k), dir = k === "A" ? -1 : 1;
      const storm = P(e, "siege", t), bo = P(k, "breakout", t);
      h.supply -= 1;
      const starving = h.supply <= 0;
      const kill = Math.min(h.troops, h.troops * (0.004 + 0.022 * storm) * (starving ? 1.7 : 1) * rng.lognormal(sig));
      h.troops -= kill; loss[k] += kill;
      const cost = kill * (0.2 + 0.9 * storm); S[e] = Math.max(0, S[e] - cost); loss[e] += cost;
      h.pm -= 0.003 + (starving ? 0.03 : 0) + 0.008 * storm;
      const gap = dir * fS[h.sector] - dir * h.f;     // how far the main front is from the pocket (10 km units)
      const close = (end, why, back) => {
        h.end = t; h.fate = why;
        if (back > 0) S[k] += back;
        const gone = h.troops - back; loss[k] += Math.max(0, gone); h.troops = 0;
        if (why === "surrendered" || why === "destroyed") {
          const hit = 0.02 + 0.2 * gone / Math.max(1, S[k] + gone);
          morale[k] -= hit; drain[k].combat += hit; morale[e] = Math.min(1, morale[e] + 0.02);
        }
      };
      const nm = `${NAME[k]}'s pocket in the ${sectors[h.sector].name} sector`;
      if (gap <= 0.15) { const back = h.troops; notes.push([t, k, `${nm} is relieved: the main front has fought its way back to it and ${back.toFixed(1)}k troops rejoin the line.`]); close(t, "relieved", back); continue; }
      if (h.troops < 0.12 * h.start) { notes.push([t, e, `${nm} is wiped out after ${t - h.day} days.`]); close(t, "destroyed", 0); continue; }
      const giveUp = (starving ? 0.05 : 0.003) + Math.max(0, 0.35 - h.pm) * 0.4;
      if (rng.random() < giveUp) { notes.push([t, e, `${nm} surrenders after ${t - h.day} days${starving ? ", out of food and ammunition" : ""}: ${h.troops.toFixed(1)}k troops taken prisoner.`]); close(t, "surrendered", 0); continue; }
      const tryOut = bo * (0.03 + (starving ? 0.12 : 0) + (h.supply < 4 ? 0.04 : 0));
      if (rng.random() < tryOut) {
        const ok = Math.max(0.1, Math.min(0.85, 0.6 - 0.22 * gap + 0.3 * (h.pm - 0.5) - 0.2 * storm));
        if (rng.random() < ok) {
          const back = h.troops * (0.4 + 0.35 * rng.random());
          notes.push([t, k, `${nm} breaks out: ${back.toFixed(1)}k of ${h.troops.toFixed(1)}k fight their way back to the main front.`]);
          close(t, "broke out", back);
        } else {
          const lost = h.troops * 0.25; h.troops -= lost; loss[k] += lost; h.pm -= 0.08;
          notes.push([t, e, `A breakout from ${nm} fails: about ${lost.toFixed(1)}k lost.`]);
        }
      }
    }
    trHeld.push(held.filter((h) => !h.end || h.end === t).map((h) => ({ id: h.id, side: h.side, sector: h.sector, f: h.f, troops: h.troops, start: h.start, supply: Math.max(0, h.supply), fate: h.end === t ? h.fate : null, day: h.day })));
    const newFront = fS.reduce((a, f, i) => a + f * W[i], 0);
    const dp = newFront - front;
    front = newFront;
    // landings: link up within 4 days or be cut off
    for (const L of landings) {
      if (L.fate || t < L.until) continue;
      const dir = L.side === "A" ? 1 : -1;
      const nm = L.kind === "airborne" ? "airborne" : "landing";
      if (dir * fS[L.sector] >= dir * L.f - 0.5) { L.fate = "linked"; L.end = t; S[L.side] += L.force * 0.85; notes.push([t, L.side, `The ${NAME[L.side]} ${nm} force links up with the main front.`]); }
      else { L.fate = "lost"; L.end = t; morale[L.side] -= 0.04; drain[L.side].ops += 0.04; notes.push([t, other(L.side), `The ${NAME[L.side]} ${nm} force is cut off and destroyed.`]); }
    }
    // supplies and economy
    if (useRes) {
      for (const [k, sign] of [["A", 1], ["B", -1]]) {
        const e = other(k);
        const seaCut = Math.min(1, 0.1 + (1 - sea[k]) * P(e, "blockade", t));
        const cut = { water: P(k, "water_cut", t) > 0 ? 1 : seaCut, food: seaCut, fuel: seaCut };
        let fuelUnmet = 0;
        for (const r of ["water", "food", "fuel"]) {
          const deficit = (1 - Math.min(1, P(k, r + "_self", t))) * cut[r];
          stock[k][r] -= deficit;
          if (stock[k][r] < 0) {
            const unmet = Math.min(deficit, -stock[k][r]); stock[k][r] = 0;
            const hit = { water: 0.025, food: 0.02, fuel: 0.01 }[r] * unmet;
            morale[k] -= hit; drain[k][r] += hit;
            if (r === "fuel") fuelUnmet = unmet;
            if (!flags[k + r]) { flags[k + r] = 1; notes.push([t, e, { water: `${NAME[k]}'s water reserves run out. Strict rationing begins.`, food: `${NAME[k]}'s food stockpiles run out.`, fuel: `${NAME[k]}'s fuel reserves run out. Vehicles and aircraft are short of fuel.` }[r]]); }
          }
        }
        fuelPenalty[k] = 1 - 0.6 * fuelUnmet;
        const lostLand = Math.max(0, -sign * front) / Math.max(P(k, "depth", t), 0.1);
        econ[k] += 0.04 + 0.12 * (P(k, "trade_dep", t) / 100) * seaCut + 0.3 * Math.min(1, lostLand);
        const tol = P(k, "econ_tol", t);
        if (econ[k] > tol) {
          const hit = 0.008 * (econ[k] / tol); morale[k] -= hit; drain[k].econ += hit;
          if (!flags[k + "econ"]) { flags[k + "econ"] = 1; notes.push([t, e, `${NAME[k]}'s economy passes its pain threshold: about ${Math.round(econ[k])}% of a year's GDP lost.`]); }
        }
      }
    }
    for (const [k, l, sign] of [["A", lA, 1], ["B", lB, -1]]) {
      const frac = l / Math.max(S[k], 1e-6);
      S[k] -= l; loss[k] += l;
      const ms = P(k, "morale_sensitivity", t);
      const move = sign * dp, enemy = k === "A" ? "B" : "A";
      const gain = move / Math.max(P(move > 0 ? enemy : k, "depth", t), 0.1);
      const mr = G("morale_rate", t);
      morale[k] += mr * (-ms * 1.5 * frac + 0.6 * gain);
      drain[k].combat += mr * ms * 1.5 * frac; if (gain < 0) drain[k].ground += -mr * 0.6 * gain;
      morale[k] += 0.02 * (sides[k].morale - morale[k]);
      morale[k] = Math.min(1, Math.max(0, morale[k]));
      if (t > P(k, "mobilization_delay", t) && reserves[k] > 0) {
        const arrive = reserves[k] * Math.min(1, P(k, "mobilization_rate", t));
        reserves[k] -= arrive; S[k] += arrive;
      }
      S[k] += P(k, "replacement", t) * sides[k].strength;
      peak[k] = Math.max(peak[k], S[k]);
    }
    trS.push(fS.slice());
    trU.push({ A: curAlloc.A.map((x) => x * S.A), B: curAlloc.B.map((x) => x * S.B) });
    trRes.push({ A: { ...stock.A, econ: econ.A }, B: { ...stock.B, econ: econ.B } });
    trF.push(front); trA.push(S.A); trB.push(S.B); trMA.push(morale.A); trMB.push(morale.B); trLA.push(loss.A); trLB.push(loss.B);
    let aLost = null, bLost = null;
    if (front >= P("B", "depth", t)) bLost = "core territory overrun";
    if (front <= -P("A", "depth", t)) aLost = "core territory overrun";
    for (const k of ["A", "B"]) {
      let why = null;
      if (S[k] < (1 - P(k, "break_point", t)) * peak[k]) why = "army broken by losses";
      else if (morale[k] < P(k, "morale_floor", t)) {
        why = "morale / political collapse";
        const d = drain[k], tot = Object.values(d).reduce((a, b) => a + b, 0) || 1;
        const [cat, val] = ["water", "food", "fuel", "econ"].map((c) => [c, d[c]]).sort((a, b) => b[1] - a[1])[0];
        if (val / tot > 0.3) why = { water: "surrender: water runs out", food: "surrender: food runs out", fuel: "surrender: fuel runs out", econ: "surrender: economy collapses" }[cat];
      }
      if (why) { if (k === "A" && aLost === null) aLost = why; if (k === "B" && bLost === null) bLost = why; }
    }
    if (aLost && bLost) {
      if (S.A / peak.A >= S.B / peak.B) { outcome = "A"; reason = bLost; } else { outcome = "B"; reason = aLost; }
      break;
    }
    if (bLost) { outcome = "A"; reason = bLost; break; }
    if (aLost) { outcome = "B"; reason = aLost; break; }
  }
  const delays = { A: P("A", "mobilization_delay", 1), B: P("B", "mobilization_delay", 1) };
  const depth = { A: sides.A.depth, B: sides.B.depth };
  return { outcome, reason, turns: Math.min(t, maxTurns), front, lossA: loss.A, lossB: loss.B, trF, trA, trB, trMA, trMB, trLA, trLB,
    sampled, fired, ceasefire, delays, depth, trS, trU, trRes, notes, landings, trPocket, pocketsClosed, trHeld, held, sectors: sectors.map((x) => x.name),
    econTol: { A: P("A", "econ_tol", 0), B: P("B", "econ_tol", 0) } };
}

function runBatch(sc, n, seed) {
  const rng = makeRng(seed);
  const out = [];
  for (let i = 0; i < n; i++) out.push(simulateOnce(sc, rng));
  return out;
}

function analyse(runs) {
  const n = runs.length;
  const cnt = { A: 0, B: 0, stalemate: 0 };
  runs.forEach((r) => cnt[r.outcome]++);
  const p = { A: cnt.A / n, B: cnt.B / n, stalemate: cnt.stalemate / n };
  const keys = Object.keys(runs[0].sampled);
  const drivers = [];
  for (const key of keys) {
    const x = runs.map((r) => r.sampled[key] ?? 0);
    let hi, lo;
    if (key.startsWith("event:")) {
      hi = x.map((v) => v === 1); lo = x.map((v) => v === 0);
    } else {
      const s = [...x].sort((a, b) => a - b);
      const q1 = s[Math.floor((n - 1) / 3)], q2 = s[Math.ceil(2 * (n - 1) / 3)];
      if (q1 === q2) continue;
      hi = x.map((v) => v >= q2); lo = x.map((v) => v <= q1);
    }
    const nh = hi.filter(Boolean).length, nl = lo.filter(Boolean).length;
    if (nh < 5 || nl < 5) continue;
    const d = { key, nh, nl };
    for (const w of ["A", "B"]) {
      const ph = runs.filter((r, i) => hi[i] && r.outcome === w).length / nh;
      const pl = runs.filter((r, i) => lo[i] && r.outcome === w).length / nl;
      const se = Math.sqrt(ph * (1 - ph) / nh + pl * (1 - pl) / nl) || 1e-9;
      d["hi" + w] = ph; d["lo" + w] = pl; d["d" + w] = ph - pl;
      d["sig" + w] = Math.abs(ph - pl) > 2 * se && Math.abs(ph - pl) >= 0.03;
    }
    drivers.push(d);
  }
  const reasons = {};
  runs.forEach((r) => { const k = r.outcome + "|" + r.reason; reasons[k] = (reasons[k] || 0) + 1; });
  const med = (arr) => { if (!arr.length) return null; const s = [...arr].sort((a, b) => a - b); return s[Math.floor(s.length / 2)]; };
  const medTurns = {};
  for (const o of ["A", "B", "stalemate"]) medTurns[o] = med(runs.filter((r) => r.outcome === o).map((r) => r.turns));
  return { n, p, drivers, reasons, medTurns };
}

if (typeof module !== "undefined") module.exports = { simulateOnce, runBatch, analyse, makeRng };
