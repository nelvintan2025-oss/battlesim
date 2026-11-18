#!/usr/bin/env python3
"""
battlesim: a "what-if" battle simulator for hobbyists.

THIS IS A SIMPLIFIED, ABSTRACT MODEL. It is built for armchair what-if exploration
using public, open-source estimates. It is not a prediction, an intelligence product,
or a planning tool. Real wars turn on politics, alliances, leadership and luck in
ways no model this small can capture.

Model in one paragraph
----------------------
Two sides (A and B) fight in turns (e.g. weeks). Each side's effective combat power is
  strength x quality x training x morale x supply x air factor x naval factor x C2
  x terrain bonus (when fighting on its own soil).
Losses follow a noisy Lanchester "square law" (each side's losses are proportional to
the other side's effective power). The front line moves toward whichever side is weaker;
advancing into enemy territory stretches the advancer's supply. Morale falls with heavy
losses and lost ground and rises with gains. Reserves mobilise after a delay, industry
replaces losses, and a side can learn (training improves over time).
A side loses when its front is pushed past its "depth" (its strategic core falls),
when its strength drops below its break point, or when its morale collapses.
If nobody wins by the turn limit (or a ceasefire event fires) the result is a stalemate.

Every parameter can be a fixed number, a [low, high] uniform range, or a
[low, most_likely, high] triangular range. Each run samples a fresh value, which is
what lets the sensitivity analysis say which uncertain factors drive the outcome.

Usage
-----
  python battlesim.py list
  python battlesim.py run scenarios/ww2_germany_ussr.json -n 200 -o out/ww2
  python battlesim.py run scenarios/sg_my_modern.json -n 200 --set A.air=60 --seed 7
  python battlesim.py sweep scenarios/ww2_germany_ussr.json --param A.logistics \
        --values 0.5,0.6,0.7,0.8,0.9,1.0 -n 200
"""
from __future__ import annotations

import argparse
import copy
import csv
import json
import math
import os
import sys
from dataclasses import dataclass, field

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
SCEN_DIR = os.path.join(HERE, "scenarios")

# --------------------------------------------------------------------------- params

SIDE_DEFAULTS = {
    "strength": 100.0,          # frontline combat power at start (abstract units)
    "quality": 1.0,             # equipment quality multiplier
    "training": 1.0,            # training / doctrine / leadership multiplier
    "training_cap": 1.0,        # max training reachable through learning
    "learning": 0.0,            # training gained per turn (wartime learning)
    "morale": 0.8,              # starting morale / will to fight, 0..1
    "morale_sensitivity": 1.0,  # how hard losses and lost ground hit morale
    "morale_floor": 0.15,       # morale below this = collapse
    "logistics": 0.8,           # supply efficiency at home, 0..1
    "supply_range": 5.0,        # distance into enemy land at which supply halves
    "air": 50.0,                # air power index (sorties x quality, abstract)
    "naval": 0.0,               # naval power index
    "c2": 1.0,                  # command, control, ISR multiplier
    "reserves": 0.0,            # extra strength that can be mobilised
    "mobilization_delay": 0,    # turns before reserves start arriving
    "mobilization_rate": 0.1,   # fraction of remaining reserves arriving per turn
    "replacement": 0.0,         # per-turn industrial replacement, fraction of start strength
    "terrain_defense": 1.0,     # combat multiplier when fighting on own soil
    "depth": 5.0,               # how far the enemy must advance to take your core
    "break_point": 0.6,         # collapse when strength falls below (1-bp) x peak
    "posture": "defend",        # "attack" or "defend" (defender gets terrain at the border)
    "tempo": 1.0,               # speed multiplier when this side is the one gaining ground
}

GLOBAL_DEFAULTS = {
    "max_turns": 52,
    "turn_label": "week",
    "lethality": 0.03,       # fraction of enemy effective power inflicted as losses per turn
    "advance_rate": 0.5,     # max front movement per turn (distance units)
    "air_weight": 0.3,       # how much winning the air war multiplies combat power
    "naval_weight": 0.0,     # how much winning at sea multiplies combat power and supply
    "noise": 0.25,           # per-turn randomness (lognormal sigma)
    "distance_unit": "100 km",
}

PARAM_LABELS = {
    "strength": "Starting frontline strength",
    "quality": "Equipment quality",
    "training": "Training & leadership",
    "learning": "Wartime learning rate",
    "morale": "Starting morale",
    "morale_sensitivity": "Morale fragility",
    "logistics": "Logistics / supply",
    "supply_range": "Supply reach",
    "air": "Air power",
    "naval": "Naval power",
    "c2": "Command, control & ISR",
    "reserves": "Mobilisable reserves",
    "mobilization_delay": "Mobilisation delay",
    "mobilization_rate": "Mobilisation speed",
    "replacement": "Industrial replacement",
    "terrain_defense": "Home terrain advantage",
    "depth": "Strategic depth",
    "break_point": "Loss tolerance",
    "lethality": "Battlefield lethality",
    "advance_rate": "Tempo of manoeuvre",
    "tempo": "Offensive tempo",
    "air_weight": "Importance of air power",
    "naval_weight": "Importance of sea power",
    "noise": "Fog of war (randomness)",
}


def sample(spec, rng):
    """Number -> itself; [lo, hi] -> uniform; [lo, mode, hi] -> triangular."""
    if isinstance(spec, (int, float)):
        return float(spec)
    if isinstance(spec, list):
        if len(spec) == 2:
            return float(rng.uniform(spec[0], spec[1]))
        if len(spec) == 3:
            lo, mode, hi = spec
            if lo == hi:
                return float(lo)
            return float(rng.triangular(lo, mode, hi))
    if isinstance(spec, dict) and "mean" in spec:
        v = rng.normal(spec["mean"], spec.get("sd", 0.0))
        if "min" in spec:
            v = max(v, spec["min"])
        if "max" in spec:
            v = min(v, spec["max"])
        return float(v)
    return spec


def is_uncertain(spec):
    return (isinstance(spec, list) and len(spec) >= 2 and min(spec) != max(spec)) or (
        isinstance(spec, dict) and spec.get("sd", 0) > 0)


# --------------------------------------------------------------------------- scenario

def load_scenario(path):
    if not os.path.isfile(path):
        alt = os.path.join(SCEN_DIR, path)
        alt2 = alt if alt.endswith(".json") else alt + ".json"
        path = alt if os.path.isfile(alt) else alt2
    with open(path) as f:
        sc = json.load(f)
    sc.setdefault("globals", {})
    sc.setdefault("events", [])
    for k in ("A", "B"):
        if k not in sc.get("sides", {}):
            raise ValueError(f"scenario needs sides.{k}")
    return sc


def apply_overrides(sc, sets):
    """--set A.air=60  --set globals.max_turns=30  --set A.logistics=[0.5,0.9]"""
    sc = copy.deepcopy(sc)
    for s in sets or []:
        key, val = s.split("=", 1)
        try:
            val = json.loads(val)
        except json.JSONDecodeError:
            pass
        path = key.split(".")
        if path[0] in ("A", "B"):
            sc["sides"][path[0]][path[1]] = val
        elif path[0] in ("globals", "g"):
            sc["globals"][path[1]] = val
        elif path[0] == "event":
            # event.<name>.prob=0.5
            name, attr = ".".join(path[1:-1]), path[-1]
            for ev in sc["events"]:
                if ev["name"] == name:
                    ev[attr] = val
                    break
            else:
                raise ValueError(f"no event named {name!r}")
        else:
            raise ValueError(f"bad --set key {key!r}; use A.x, B.x, globals.x or event.<name>.prob")
    return sc


# --------------------------------------------------------------------------- engine

@dataclass
class RunResult:
    outcome: str                 # "A", "B", "stalemate"
    reason: str
    turns: int
    front: float
    lossA: float
    lossB: float
    traj_sA: list = field(default_factory=list)
    traj_sB: list = field(default_factory=list)
    traj_front: list = field(default_factory=list)


def simulate_once(sc, rng):
    g = dict(GLOBAL_DEFAULTS)
    sampled = {}
    for k, v in sc["globals"].items():
        g[k] = sample(v, rng)
        if is_uncertain(v):
            sampled[f"globals.{k}"] = g[k]
    sides = {}
    for key in ("A", "B"):
        p = dict(SIDE_DEFAULTS)
        for k, v in sc["sides"][key].items():
            if k == "name":
                continue
            p[k] = sample(v, rng)
            if is_uncertain(v):
                sampled[f"{key}.{k}"] = p[k]
        sides[key] = p

    # events: each fires with prob; effects apply in a turn window
    fired = []
    mods = []          # (side, param, mult, add, from_turn, to_turn)
    ceasefire = None
    for ev in sc["events"]:
        hit = rng.random() < sample(ev.get("prob", 0.5), rng)
        sampled[f"event:{ev['name']}"] = 1.0 if hit else 0.0
        if not hit:
            effects = ev.get("else_effects", [])
        else:
            fired.append(ev["name"])
            effects = ev.get("effects", [])
        if hit and "ceasefire_turn" in ev:
            ct = int(round(sample(ev["ceasefire_turn"], rng)))
            ceasefire = ct if ceasefire is None else min(ceasefire, ct)
        for eff in effects:
            mods.append((eff["side"], eff["param"], sample(eff.get("mult", 1.0), rng),
                         sample(eff.get("add", 0.0), rng),
                         int(eff.get("from_turn", 0)), int(eff.get("to_turn", 10**9))))

    def P(side, name, t):
        v = sides[side][name]
        if isinstance(v, str):
            return v
        for s, n, m, a, f0, f1 in mods:
            if (s == side or s == "both") and n == name and f0 <= t <= f1:
                v = v * m + a
        return v

    def G(name, t):
        v = g[name]
        for s, n, m, a, f0, f1 in mods:
            if s == "globals" and n == name and f0 <= t <= f1:
                v = v * m + a
        return v

    S = {k: P(k, "strength", 0) for k in "AB"}
    peak = dict(S)
    morale = {k: P(k, "morale", 0) for k in "AB"}
    training = {k: P(k, "training", 0) for k in "AB"}
    reserves = {k: P(k, "reserves", 0) for k in "AB"}
    loss = {"A": 0.0, "B": 0.0}
    front = 0.0   # >0 = inside B's territory, <0 = inside A's
    max_turns = int(G("max_turns", 0))
    if ceasefire is not None:
        max_turns = min(max_turns, ceasefire)
    tr_sA, tr_sB, tr_f = [S["A"]], [S["B"]], [front]
    outcome, reason, t = "stalemate", "turn limit", 0
    if ceasefire is not None and ceasefire <= G("max_turns", 0):
        reason = "ceasefire imposed"

    for t in range(1, max_turns + 1):
        # air & sea control
        airA, airB = max(P("A", "air", t), 0.01), max(P("B", "air", t), 0.01)
        air_share = airA ** 1.5 / (airA ** 1.5 + airB ** 1.5)
        navA, navB = max(P("A", "naval", t), 0.01), max(P("B", "naval", t), 0.01)
        nav_share = navA ** 1.5 / (navA ** 1.5 + navB ** 1.5)
        aw, nw = G("air_weight", t), G("naval_weight", t)
        air_mult = {"A": 1 + aw * (2 * air_share - 1), "B": 1 + aw * (1 - 2 * air_share)}
        nav_mult = {"A": 1 + nw * (2 * nav_share - 1), "B": 1 + nw * (1 - 2 * nav_share)}

        E = {}
        for k, sign in (("A", 1), ("B", -1)):
            depth_in = max(0.0, sign * front)          # how far k is inside enemy land
            supply = P(k, "logistics", t) / (1 + depth_in / max(P(k, "supply_range", t), 0.1))
            supply *= 0.5 + 0.5 * nav_mult[k]          # sea control protects supply lines
            on_home = sign * front < 0 or (front == 0 and sides[k]["posture"] == "defend")
            terrain = P(k, "terrain_defense", t) if on_home else 1.0
            morale_eff = 0.4 + 0.6 * morale[k]
            training[k] = min(training[k] + P(k, "learning", t), max(P(k, "training_cap", t), sides[k]["training"]))
            E[k] = (S[k] * P(k, "quality", t) * training[k] * morale_eff * supply
                    * air_mult[k] * nav_mult[k] * P(k, "c2", t) * terrain)

        sig = G("noise", t)
        leth = G("lethality", t)
        lA = min(S["A"], leth * E["B"] * rng.lognormal(0, sig))
        lB = min(S["B"], leth * E["A"] * rng.lognormal(0, sig))
        ratio = max(E["A"], 1e-6) / max(E["B"], 1e-6)
        push = math.tanh(1.2 * math.log(ratio))
        dp = G("advance_rate", t) * push * rng.lognormal(0, sig) * P("A" if push >= 0 else "B", "tempo", t)
        front += dp

        for k, l, sign in (("A", lA, 1), ("B", lB, -1)):
            frac = l / max(S[k], 1e-6)
            S[k] -= l
            loss[k] += l
            ms = P(k, "morale_sensitivity", t)
            move = sign * dp   # >0 = this side gained ground
            enemy = "B" if k == "A" else "A"
            # gains count against the enemy's depth, losses against your own
            gain = move / max(P(enemy if move > 0 else k, "depth", t), 0.1)
            morale[k] += -ms * 1.5 * frac + 0.6 * gain
            morale[k] += 0.02 * (sides[k]["morale"] - morale[k])  # slow recovery toward baseline
            morale[k] = min(1.0, max(0.0, morale[k]))
            # reinforcements
            if t > P(k, "mobilization_delay", t) and reserves[k] > 0:
                arrive = reserves[k] * min(1.0, P(k, "mobilization_rate", t))
                reserves[k] -= arrive
                S[k] += arrive
            S[k] += P(k, "replacement", t) * sides[k]["strength"]
            peak[k] = max(peak[k], S[k])

        tr_sA.append(S["A"]); tr_sB.append(S["B"]); tr_f.append(front)

        # termination
        a_lost = b_lost = None
        if front >= P("B", "depth", t):
            b_lost = "core territory overrun"
        if front <= -P("A", "depth", t):
            a_lost = "core territory overrun"
        for k in "AB":
            why = None
            if S[k] < (1 - P(k, "break_point", t)) * peak[k]:
                why = "army broken by losses"
            elif morale[k] < P(k, "morale_floor", t):
                why = "morale / political collapse"
            if why:
                if k == "A" and a_lost is None:
                    a_lost = why
                if k == "B" and b_lost is None:
                    b_lost = why
        if a_lost and b_lost:
            # both collapse the same turn: side with the higher remaining power ratio wins
            if S["A"] / peak["A"] >= S["B"] / peak["B"]:
                outcome, reason = "A", b_lost
            else:
                outcome, reason = "B", a_lost
            break
        if b_lost:
            outcome, reason = "A", b_lost
            break
        if a_lost:
            outcome, reason = "B", a_lost
            break

    return RunResult(outcome, reason, t, front, loss["A"], loss["B"], tr_sA, tr_sB, tr_f), sampled, fired


def run_batch(sc, n, seed=None):
    rng = np.random.default_rng(seed)
    rows, results = [], []
    for i in range(n):
        res, sampled, fired = simulate_once(sc, rng)
        results.append(res)
        row = {"run": i + 1, "outcome": res.outcome, "reason": res.reason, "turns": res.turns,
               "final_front": round(res.front, 3), "lossA": round(res.lossA, 2),
               "lossB": round(res.lossB, 2), "events": "|".join(fired)}
        row.update({k: round(v, 4) for k, v in sampled.items()})
        rows.append(row)
    return rows, results


# --------------------------------------------------------------------------- analysis

def outcome_score(o):
    return {"A": 1.0, "stalemate": 0.5, "B": 0.0}[o]


def _rank(x):
    order = np.argsort(x, kind="mergesort")
    r = np.empty(len(x))
    r[order] = np.arange(len(x))
    # average ties
    xs = np.asarray(x)[order]
    i = 0
    while i < len(xs):
        j = i
        while j + 1 < len(xs) and xs[j + 1] == xs[i]:
            j += 1
        if j > i:
            r[order[i:j + 1]] = (i + j) / 2
        i = j + 1
    return r


def spearman(x, y):
    if np.std(x) == 0 or np.std(y) == 0:
        return 0.0
    return float(np.corrcoef(_rank(x), _rank(y))[0, 1])


def label_for(key, sc):
    if key.startswith("event:"):
        return "Event: " + key[6:]
    side, name = key.split(".", 1)
    if side == "globals":
        return PARAM_LABELS.get(name, name)
    lbl = PARAM_LABELS.get(name, name)
    return f"{sc['sides'][side].get('name', side)} {lbl[0].lower() + lbl[1:]}"


def analyse(sc, rows):
    n = len(rows)
    outcomes = [r["outcome"] for r in rows]
    score = np.array([outcome_score(o) for o in outcomes])
    winA = np.array([1.0 if o == "A" else 0.0 for o in outcomes])
    winB = np.array([1.0 if o == "B" else 0.0 for o in outcomes])
    keys = [k for k in rows[0] if "." in k or k.startswith("event:")]
    drivers = []
    for k in keys:
        x = np.array([r.get(k, 0.0) for r in rows], dtype=float)
        if np.std(x) == 0:
            continue
        rho = spearman(x, score)
        if k.startswith("event:"):
            hi, lo = x == 1, x == 0
            hi_lbl, lo_lbl = "happens", "doesn't happen"
        else:
            q1, q2 = np.quantile(x, [1 / 3, 2 / 3])
            lo, hi = x <= q1, x >= q2
            hi_lbl = f"high (>= {q2:.3g})"
            lo_lbl = f"low (<= {q1:.3g})"
        if hi.sum() < 3 or lo.sum() < 3:
            continue
        drivers.append({
            "key": k, "label": label_for(k, sc), "rho": rho,
            "winA_high": float(winA[hi].mean()), "winA_low": float(winA[lo].mean()),
            "winB_high": float(winB[hi].mean()), "winB_low": float(winB[lo].mean()),
            "n_high": int(hi.sum()), "n_low": int(lo.sum()),
            "hi_label": hi_lbl, "lo_label": lo_lbl,
            "swing": float(winA[hi].mean() - winA[lo].mean()),
            "swing_score": float(score[hi].mean() - score[lo].mean()),
            "dA": float(winA[hi].mean() - winA[lo].mean()),
            "dB": float(winB[hi].mean() - winB[lo].mean()),
        })
        d = drivers[-1]
        se = math.sqrt(np.var(score[hi]) / hi.sum() + np.var(score[lo]) / lo.sum())
        d["se"] = se
        for w, arr in (("A", winA), ("B", winB)):
            ph, pl = arr[hi].mean(), arr[lo].mean()
            sew = math.sqrt(ph * (1 - ph) / hi.sum() + pl * (1 - pl) / lo.sum()) or 1e-9
            d["sig" + w] = bool(abs(ph - pl) > 2 * sew and abs(ph - pl) >= 0.03)
        d["significant"] = bool(abs(d["swing_score"]) > 2 * se and abs(d["swing_score"]) >= 0.03)
    drivers.sort(key=lambda d: -abs(d["swing_score"]))

    reasons = {}
    for r in rows:
        key = (r["outcome"], r["reason"])
        reasons[key] = reasons.get(key, 0) + 1

    turns = np.array([r["turns"] for r in rows])
    p = {o: outcomes.count(o) / n for o in ("A", "B", "stalemate")}
    ci = {o: 1.96 * math.sqrt(max(p[o] * (1 - p[o]), 1e-9) / n) for o in p}
    return {
        "n": n, "p": p, "ci95": ci,
        "median_turns": {o: float(np.median(turns[[x == o for x in outcomes]])) if o in outcomes else None
                         for o in ("A", "B", "stalemate")},
        "reasons": {f"{o}|{why}": c for (o, why), c in sorted(reasons.items(), key=lambda kv: -kv[1])},
        "drivers": drivers,
        "mean_lossA": float(np.mean([r["lossA"] for r in rows])),
        "mean_lossB": float(np.mean([r["lossB"] for r in rows])),
    }


def effect_phrase(d, A, B):
    """Describe a driver: who it helps, and whether it mostly creates stalemates."""
    dA, dB = d["dA"] * 100, d["dB"] * 100
    helped = A if d["swing_score"] > 0 else B
    if dA < 0 and dB < 0:
        return f"turns wins into stalemates ({A} {dA:+.0f}, {B} {dB:+.0f} pts)"
    loser_d, helped_d = (dB, dA) if d["swing_score"] > 0 else (dA, dB)
    other = B if d["swing_score"] > 0 else A
    if abs(helped_d) < 0.3 * abs(loser_d):
        return f"mostly denies {other} a win; draws more likely ({A} {dA:+.0f}, {B} {dB:+.0f} pts)"
    if dA > 0 and dB > 0:
        return f"fewer stalemates ({A} {dA:+.0f}, {B} {dB:+.0f} pts)"
    return f"favours {helped} ({A} {dA:+.0f}, {B} {dB:+.0f} pts)"


def narrative(sc, a):
    A = sc["sides"]["A"].get("name", "Side A")
    B = sc["sides"]["B"].get("name", "Side B")
    unit = sc["globals"].get("turn_label", GLOBAL_DEFAULTS["turn_label"])
    p, ci = a["p"], a["ci95"]
    L = []
    L.append(f"# {sc.get('title', 'Scenario')}: simulation report\n")
    L.append("> Simplified abstract model for hobbyist what-if exploration, built on public "
             "open-source estimates. Not a forecast. Treat the numbers as *relative*, not literal.\n")
    if sc.get("description"):
        L.append(sc["description"] + "\n")
    L.append(f"## Headline ({a['n']} runs)\n")
    for o, nm in (("A", A), ("B", B), ("stalemate", "Stalemate / ceasefire")):
        mt = a["median_turns"][o]
        extra = f", median {mt:.0f} {unit}s" if mt is not None else ""
        L.append(f"- **{nm}**: {p[o]*100:.0f}% (±{ci[o]*100:.0f} pts{extra})")
    L.append("")
    L.append("## How the wars ended\n")
    for k, c in a["reasons"].items():
        o, why = k.split("|", 1)
        if o == "stalemate":
            L.append(f"- No decision ({why}): {c} runs ({c / a['n'] * 100:.0f}%)")
        else:
            win, lose = (A, B) if o == "A" else (B, A)
            L.append(f"- {win} wins, {lose}'s {why}: {c} runs ({c / a['n'] * 100:.0f}%)")
    stal = [r for r in a.get("_rows", []) if r["outcome"] == "stalemate"]
    if stal:
        inB = sum(1 for r in stal if r["final_front"] > 0.05)
        inA = sum(1 for r in stal if r["final_front"] < -0.05)
        L.append(f"\nIn the {len(stal)} undecided runs the front ended inside {B} in {inB}, "
                 f"inside {A} in {inA}, and near the start line in {len(stal) - inA - inB}.")
    L.append("")
    if a["n"] < 1000:
        L.append(f"_Note: with {a['n']} runs, effects smaller than about ±10 points are hard to tell from luck. "
                 f"Use `-n 1000` or more for steadier driver rankings._\n")

    top = [d for d in a["drivers"] if d["significant"]][:8]
    weak = [d for d in a["drivers"] if not d["significant"]]
    if top:
        L.append("## What decides it\n")
        L.append(f"Ranked by how much the outcome swings between the top and bottom third of each "
                 f"uncertain factor (or whether an event happens).\n")
        L.append(f"| Factor | When high / it happens | When low / it doesn't | Effect |")
        L.append("|---|---|---|---|")
        for d in top:
            L.append(f"| {d['label']} | {A} {d['winA_high']*100:.0f}% · {B} {d['winB_high']*100:.0f}% "
                     f"| {A} {d['winA_low']*100:.0f}% · {B} {d['winB_low']*100:.0f}% "
                     f"| {effect_phrase(d, A, B)} |")
        L.append("")
        if weak:
            L.append("Within the noise at this run count (no clear effect): "
                     + ", ".join(d["label"] for d in weak[:12]) + ".\n")

        def cond(d, w):
            dw = d["d" + w]
            hi_p, lo_p = d["win%s_high" % w] * 100, d["win%s_low" % w] * 100
            if d["key"].startswith("event:"):
                what = f"*{d['key'][6:]}* {'happens' if dw > 0 else 'does not happen'}"
                return f"{what} ({max(hi_p, lo_p):.0f}% vs {min(hi_p, lo_p):.0f}%)"
            lbl = d["label"]
            return f"{lbl} is {'high' if dw > 0 else 'low'} ({max(hi_p, lo_p):.0f}% vs {min(hi_p, lo_p):.0f}%)"

    for w, nm in (("A", A), ("B", B)):
        ds = sorted([d for d in a["drivers"] if d.get("sig" + w)], key=lambda d: -abs(d["d" + w]))[:5]
        L.append(f"## When does {nm} win?\n")
        if not ds:
            L.append(f"No single factor clearly moves {nm}'s odds at this run count.\n")
            continue
        L.append(f"{nm} wins {a['p'][w]*100:.0f}% overall. Its odds move most when:\n")
        for d in ds:
            L.append(f"- {cond(d, w)}")
        L.append("")
    L.append("## Caveats\n")
    L.append("- Lanchester-style attrition with multiplicative modifiers; no geography, no individual units, "
             "no diplomacy beyond the scripted events.\n- Inputs are rough public estimates with wide ranges; "
             "change them with `--set` and see how fragile each conclusion is.\n"
             "- 'Drivers' are correlations inside this model, not proof of real-world causation.")
    if sc.get("sources"):
        L.append("\n## Public sources behind the inputs\n")
        for s in sc["sources"]:
            L.append(f"- {s}")
    return "\n".join(L) + "\n"


# --------------------------------------------------------------------------- charts

INK, INK2, MUTED, GRID, SURF = "#0b0b0b", "#52514e", "#8a8984", "#e6e5e1", "#fcfcfb"
C_A, C_B, C_S = "#2a78d6", "#eb6834", "#a3a29c"


def _style():
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    plt.rcParams.update({
        "figure.facecolor": SURF, "axes.facecolor": SURF, "savefig.facecolor": SURF,
        "axes.edgecolor": GRID, "axes.labelcolor": INK2, "xtick.color": INK2, "ytick.color": INK2,
        "axes.grid": True, "grid.color": GRID, "grid.linewidth": 0.8, "axes.axisbelow": True,
        "axes.spines.top": False, "axes.spines.right": False, "font.size": 10,
        "axes.titlesize": 12, "axes.titleweight": "bold", "axes.titlecolor": INK,
        "axes.titlelocation": "left", "legend.frameon": False, "text.color": INK,
    })
    return plt


def chart_outcomes(ax, sc, a):
    A = sc["sides"]["A"].get("name", "A"); B = sc["sides"]["B"].get("name", "B")
    labels = [f"{A} wins", f"{B} wins", "Stalemate"]
    vals = [a["p"]["A"] * 100, a["p"]["B"] * 100, a["p"]["stalemate"] * 100]
    errs = [a["ci95"][o] * 100 for o in ("A", "B", "stalemate")]
    bars = ax.barh(labels[::-1], vals[::-1], color=[C_S, C_B, C_A], height=0.55,
                   xerr=errs[::-1], error_kw={"ecolor": MUTED, "lw": 1, "capsize": 3})
    for b, v, e in zip(bars, vals[::-1], errs[::-1]):
        ax.text(b.get_width() + e + 2, b.get_y() + b.get_height() / 2, f"{v:.0f}%", va="center", color=INK)
    ax.set_xlim(0, 110)
    ax.set_xlabel("Share of runs (%) — whiskers are 95% intervals")
    ax.set_title(f"Who wins? ({a['n']} runs)")
    ax.grid(axis="y", visible=False)


def chart_duration(ax, sc, rows):
    A = sc["sides"]["A"].get("name", "A"); B = sc["sides"]["B"].get("name", "B")
    unit = sc["globals"].get("turn_label", "week")
    mx = max(r["turns"] for r in rows)
    bins = np.linspace(0, mx + 1, min(30, mx + 2))
    data = [[r["turns"] for r in rows if r["outcome"] == o] for o in ("A", "B", "stalemate")]
    ax.hist(data, bins=bins, stacked=True, color=[C_A, C_B, C_S], edgecolor=SURF, linewidth=1,
            label=[f"{A} wins", f"{B} wins", "Stalemate"])
    ax.set_xlabel(f"War length ({unit}s)")
    ax.set_ylabel("Runs")
    ax.set_title("How long does it last?")
    ax.legend(loc="upper right")
    ax.grid(axis="x", visible=False)


def chart_trajectories(ax, sc, results):
    A = sc["sides"]["A"].get("name", "A"); B = sc["sides"]["B"].get("name", "B")
    unit = sc["globals"].get("turn_label", "week")
    T = Tfull = max(len(r.traj_sA) for r in results)

    def mat(attr):
        M = np.full((len(results), Tfull), np.nan)
        for i, r in enumerate(results):
            tr = getattr(r, attr)
            M[i, :len(tr)] = tr       # NaN after a war ends: only ongoing wars are counted
        return M
    alive = np.array([sum(len(r.traj_sA) > t for r in results) for t in range(Tfull)])
    T = max(2, int(np.argmax(alive < 0.1 * len(results))) or Tfull)   # stop once <10% of wars still running
    x = np.arange(T)
    for attr, col, nm in (("traj_sA", C_A, A), ("traj_sB", C_B, B)):
        M = mat(attr)
        lo, med, hi = np.nanpercentile(M[:, :T], [10, 50, 90], axis=0)
        ax.fill_between(x, lo, hi, color=col, alpha=0.15, linewidth=0)
        ax.plot(x, med, color=col, lw=2, label=f"{nm} (median, 10–90% band)")
    ax.set_xlabel(unit.capitalize())
    ax.set_ylabel("Combat strength (abstract units)")
    ax.set_title("Strength over time (wars still running)")
    ax.legend(loc="best")


def chart_front(ax, sc, results):
    A = sc["sides"]["A"].get("name", "A"); B = sc["sides"]["B"].get("name", "B")
    unit = sc["globals"].get("turn_label", "week")
    du = sc["globals"].get("distance_unit", GLOBAL_DEFAULTS["distance_unit"])
    for r in results[:80]:
        col = {"A": C_A, "B": C_B, "stalemate": C_S}[r.outcome]
        ax.plot(r.traj_front, color=col, lw=0.8, alpha=0.45)
    ax.axhline(0, color=INK2, lw=1)
    ax.set_xlabel(unit.capitalize())
    ax.set_ylabel(f"Front line ({du}); + = inside {B}")
    ax.set_title("Where is the front? (first 80 runs)")
    from matplotlib.lines import Line2D
    ax.legend([Line2D([], [], color=c, lw=2) for c in (C_A, C_B, C_S)],
              [f"{A} wins", f"{B} wins", "Stalemate"], loc="best")


def chart_drivers(ax, sc, a, k=10):
    A = sc["sides"]["A"].get("name", "A"); B = sc["sides"]["B"].get("name", "B")
    ds = a["drivers"][:k][::-1]
    if not ds:
        ax.text(0.5, 0.5, "No uncertain inputs to analyse", ha="center", transform=ax.transAxes)
        return
    y = np.arange(len(ds))
    h = 0.36
    vA = [d["dA"] * 100 for d in ds]
    vB = [d["dB"] * 100 for d in ds]
    alpha = [1.0 if d["significant"] else 0.35 for d in ds]
    for i in range(len(ds)):
        ax.barh(y[i] + h / 2, vA[i], height=h, color=C_A, alpha=alpha[i], edgecolor=SURF, lw=1)
        ax.barh(y[i] - h / 2, vB[i], height=h, color=C_B, alpha=alpha[i], edgecolor=SURF, lw=1)
    ax.set_yticks(y)
    ax.set_yticklabels([d["label"] + ("" if d["significant"] else "  (noise)") for d in ds])
    for t, d in zip(ax.get_yticklabels(), ds):
        t.set_color(INK if d["significant"] else MUTED)
    ax.axvline(0, color=INK2, lw=1)
    lim = max(10, max(abs(v) for v in vA + vB) * 1.2)
    ax.set_xlim(-lim, lim)
    for i in range(len(ds)):
        if not ds[i]["significant"]:
            continue
        for v, off in ((vA[i], h / 2), (vB[i], -h / 2)):
            ax.text(v + (1 if v >= 0 else -1) * lim * 0.015, y[i] + off, f"{v:+.0f}", va="center",
                    ha="left" if v >= 0 else "right", color=INK2, fontsize=8)
    from matplotlib.patches import Patch
    ax.legend([Patch(color=C_A), Patch(color=C_B)], [f"Change in {A} win %", f"Change in {B} win %"],
              loc="lower right")
    ax.set_xlabel("Win-rate change when the factor is high (top third) vs low (bottom third), or the event happens vs not (pts)")
    ax.set_title("What decides the outcome?")
    ax.grid(axis="y", visible=False)


def make_charts(sc, a, rows, results, outdir):
    plt = _style()
    paths = {}
    single = [("outcomes", lambda ax: chart_outcomes(ax, sc, a), (7, 3.2)),
              ("duration", lambda ax: chart_duration(ax, sc, rows), (7, 4)),
              ("strength", lambda ax: chart_trajectories(ax, sc, results), (7, 4)),
              ("front", lambda ax: chart_front(ax, sc, results), (7, 4)),
              ("drivers", lambda ax: chart_drivers(ax, sc, a), (9, 5))]
    for name, fn, size in single:
        fig, ax = plt.subplots(figsize=size, dpi=150)
        fn(ax)
        fig.tight_layout()
        p = os.path.join(outdir, f"{name}.png")
        fig.savefig(p)
        plt.close(fig)
        paths[name] = p

    fig = plt.figure(figsize=(15, 11), dpi=130)
    gs = fig.add_gridspec(3, 2, height_ratios=[0.8, 1, 1.2], hspace=0.45, wspace=0.28)
    chart_outcomes(fig.add_subplot(gs[0, 0]), sc, a)
    chart_duration(fig.add_subplot(gs[0, 1]), sc, rows)
    chart_trajectories(fig.add_subplot(gs[1, 0]), sc, results)
    chart_front(fig.add_subplot(gs[1, 1]), sc, results)
    chart_drivers(fig.add_subplot(gs[2, :]), sc, a, k=10)
    drv_ax = fig.axes[-1]
    fig.suptitle(f"{sc.get('title', 'Scenario')} — {a['n']} simulated runs", x=0.06, ha="left",
                 fontsize=15, fontweight="bold", color=INK)
    fig.text(0.06, 0.945, "Simplified abstract model for hobbyist what-if exploration, using public "
             "open-source estimates. Not a forecast.", fontsize=10, color=INK2)
    fig.subplots_adjust(top=0.91, left=0.17, right=0.97, bottom=0.05)
    pos = drv_ax.get_position()
    drv_ax.set_position([0.30, pos.y0, 0.97 - 0.30, pos.height])
    p = os.path.join(outdir, "dashboard.png")
    fig.savefig(p)
    plt.close(fig)
    paths["dashboard"] = p
    return paths


# --------------------------------------------------------------------------- commands

def cmd_run(args):
    sc = apply_overrides(load_scenario(args.scenario), args.set)
    rows, results = run_batch(sc, args.n, args.seed)
    a = analyse(sc, rows)
    out = args.out or os.path.join("out", os.path.splitext(os.path.basename(args.scenario))[0])
    os.makedirs(out, exist_ok=True)
    keys = list(dict.fromkeys(k for r in rows for k in r))
    with open(os.path.join(out, "runs.csv"), "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=keys)
        w.writeheader()
        w.writerows(rows)
    with open(os.path.join(out, "summary.json"), "w") as f:
        json.dump({"scenario": sc.get("title"), "overrides": args.set or [], **a}, f, indent=2)
    report = narrative(sc, {**a, "_rows": rows})
    with open(os.path.join(out, "report.md"), "w") as f:
        f.write(report)
    if not args.no_charts:
        make_charts(sc, a, rows, results, out)
    A = sc["sides"]["A"].get("name", "A"); B = sc["sides"]["B"].get("name", "B")
    print(f"{sc.get('title')}: {args.n} runs")
    print(f"  {A} wins {a['p']['A']*100:.1f}% | {B} wins {a['p']['B']*100:.1f}% | "
          f"stalemate {a['p']['stalemate']*100:.1f}%")
    print("  Top drivers:")
    for d in [d for d in a["drivers"] if d["significant"]][:6]:
        print(f"    {d['label']}: {effect_phrase(d, A, B)}")
    print(f"  Outputs in {out}/ (report.md, dashboard.png, runs.csv, summary.json)")


def cmd_sweep(args):
    base = load_scenario(args.scenario)
    vals = [json.loads(v) for v in args.values.split(",")]
    nA = base["sides"]["A"].get("name", "A"); nB = base["sides"]["B"].get("name", "B")
    res = []
    for v in vals:
        sc = apply_overrides(base, (args.set or []) + [f"{args.param}={json.dumps(v)}"])
        rows, _ = run_batch(sc, args.n, args.seed)
        a = analyse(sc, rows)
        res.append((v, a["p"]))
        print(f"  {args.param}={v}: {nA} {a['p']['A']*100:.0f}%  {nB} {a['p']['B']*100:.0f}%  "
              f"stalemate {a['p']['stalemate']*100:.0f}%")
    out = args.out or "out"
    os.makedirs(out, exist_ok=True)
    plt = _style()
    A = base["sides"]["A"].get("name", "A"); B = base["sides"]["B"].get("name", "B")
    fig, ax = plt.subplots(figsize=(7.5, 4.2), dpi=150)
    xs = [r[0] for r in res]
    for o, col, nm in (("A", C_A, f"{A} wins"), ("B", C_B, f"{B} wins"), ("stalemate", C_S, "Stalemate")):
        ys = [r[1][o] * 100 for r in res]
        ax.plot(xs, ys, color=col, lw=2, marker="o", ms=6, label=nm)
        ax.annotate(nm, (xs[-1], ys[-1]), xytext=(6, 0), textcoords="offset points", va="center", color=INK2)
    ax.set_ylim(0, 100)
    ax.set_ylabel("Share of runs (%)")
    key = args.param.split(".")
    if key[0] == "event":
        xl = f"Probability that '{'.'.join(key[1:-1])}' happens"
        title = f"What if: '{'.'.join(key[1:-1])}' becomes more likely"
    else:
        xl = label_for(args.param if key[0] != "g" else "globals." + key[1], base)
        title = f"What if: {xl[0].lower() + xl[1:] if key[0] == 'globals' else xl} changes"
    ax.set_xlabel(xl)
    ax.set_title(title)
    ax.legend(loc="upper left")
    fig.tight_layout()
    import re
    p = os.path.join(out, "sweep_" + re.sub(r"[^A-Za-z0-9]+", "_", args.param).strip("_").lower() + ".png")
    fig.savefig(p)
    print(f"  Chart: {p}")


def cmd_list(_args):
    for fn in sorted(os.listdir(SCEN_DIR)):
        if fn.endswith(".json"):
            with open(os.path.join(SCEN_DIR, fn)) as f:
                sc = json.load(f)
            print(f"{fn}: {sc.get('title')} — {sc['sides']['A'].get('name')} vs {sc['sides']['B'].get('name')}")


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[1])
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run", help="run N simulations and write report + charts")
    r.add_argument("scenario")
    r.add_argument("-n", type=int, default=200)
    r.add_argument("-o", "--out")
    r.add_argument("--seed", type=int)
    r.add_argument("--set", action="append", help="override, e.g. A.air=60 or globals.max_turns=30")
    r.add_argument("--no-charts", action="store_true")
    r.set_defaults(fn=cmd_run)
    s = sub.add_parser("sweep", help="vary one parameter and chart win rates")
    s.add_argument("scenario")
    s.add_argument("--param", required=True)
    s.add_argument("--values", required=True, help="comma separated, e.g. 0.5,0.7,0.9")
    s.add_argument("-n", type=int, default=200)
    s.add_argument("-o", "--out")
    s.add_argument("--seed", type=int)
    s.add_argument("--set", action="append")
    s.set_defaults(fn=cmd_sweep)
    l = sub.add_parser("list", help="list bundled scenarios")
    l.set_defaults(fn=cmd_list)
    args = ap.parse_args(argv)
    args.fn(args)


if __name__ == "__main__":
    main()
