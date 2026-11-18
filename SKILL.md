---
name: battle-sim
description: Run what-if battle simulations (e.g. 200+ runs) between two military forces, chart the outcomes, and explain which factors and circumstances decide who wins. Use for hobbyist military history or hypothetical matchups such as WW2 Germany vs USSR or a modern Singapore vs Malaysia scenario.
---

# Battle simulation (what-if)

A simplified, abstract model for hobbyist what-if exploration, driven by `battlesim.py`
in this folder. It uses only public open-source estimates. Always say so when presenting
results: the numbers are relative and illustrative, not a forecast.

## When asked to simulate a matchup

1. **Pick or write a scenario.** Bundled ones live in `scenarios/` (`python battlesim.py list`).
   For a new matchup, copy the closest bundled JSON and edit it (format below). Use public
   figures only (IISS Military Balance, SIPRI, Wikipedia, standard histories) and put them
   in `sources`. Give uncertain inputs a range rather than one number: the ranges are what
   make the "what decides it" analysis work.
2. **Run it.** `python battlesim.py run <scenario> -n 1000 --seed 1 -o out/<name>`
   (`-n 200` is fine for a quick look, but driver rankings are noisy below ~1000 runs; it
   runs ~1000 sims per second).
3. **Explore what-ifs** the user asks about:
   - One-off change: `--set A.air=120`, `--set B.logistics=[0.5,0.7]`, `--set globals.max_turns=30`,
     `--set "event.Lend-Lease at scale.prob=0"`.
   - Curve over a range: `python battlesim.py sweep <scenario> --param A.logistics --values 0.5,0.7,0.9,1.0 -n 1000`.
4. **Present the results.** Show `dashboard.png` (and any sweep chart), then summarise
   `report.md` in plain words: who wins how often, how wars end, and the top factors for
   each side from the "When does X win?" sections. Mention that factors marked "noise" had no
   clear effect, and that drivers are correlations inside the model.

## Outputs (in the `-o` folder)

| File | What it is |
|---|---|
| `dashboard.png` | Win rates, war length, strength over time, front line, and the drivers chart |
| `outcomes.png`, `duration.png`, `strength.png`, `front.png`, `drivers.png` | The same charts singly |
| `report.md` | Headline odds, how wars ended, driver table, "When does X win?" for each side, sources |
| `summary.json` | Machine-readable version of the analysis |
| `runs.csv` | One row per run: sampled inputs, events that fired, outcome |

## Scenario format (JSON)

```json
{
  "title": "...", "description": "...", "sources": ["..."],
  "globals": {"max_turns": 52, "turn_label": "week", "distance_unit": "100 km",
              "lethality": 0.03, "advance_rate": [0.3, 0.5], "air_weight": 0.3,
              "naval_weight": 0.0, "noise": 0.25},
  "sides": {
    "A": {"name": "Side A", "posture": "attack", "strength": [90, 100, 110], "...": "..."},
    "B": {"name": "Side B", "posture": "defend", "...": "..."}
  },
  "events": [
    {"name": "Harsh winter", "prob": 0.5,
     "effects": [{"side": "A", "param": "logistics", "mult": 0.6, "from_turn": 16, "to_turn": 30}],
     "else_effects": []},
    {"name": "Ceasefire", "prob": 0.5, "ceasefire_turn": [5, 10, 20]}
  ]
}
```

Values: a number, `[low, high]` (uniform) or `[low, most_likely, high]` (triangular).
Event effects use `mult` and/or `add` on a side parameter (`side` is `A`, `B`, `both` or
`globals`), optionally only between `from_turn` and `to_turn`.

Side parameters (defaults in `SIDE_DEFAULTS` in `battlesim.py`):

| Param | Meaning |
|---|---|
| `strength` | Frontline combat power at start (e.g. thousands of troops-equivalent) |
| `quality`, `training`, `c2` | Equipment, training/leadership, command-control-ISR multipliers (~0.3 to 1.3) |
| `learning`, `training_cap` | Training gained per turn, and its ceiling (wartime learning) |
| `morale`, `morale_sensitivity`, `morale_floor` | Starting will to fight (0 to 1), how hard losses and lost ground hit it, collapse threshold |
| `logistics`, `supply_range` | Supply efficiency at home; distance into enemy land at which supply halves |
| `air`, `naval` | Air and naval power indices; only the ratio between sides matters |
| `reserves`, `mobilization_delay`, `mobilization_rate` | Mobilisable strength, turns before it arrives, share of remaining reserves arriving per turn |
| `replacement` | Per-turn industrial replacement as a share of starting strength |
| `terrain_defense` | Combat multiplier on own soil (urban / mountains / forest are higher) |
| `depth` | How far the enemy must advance to take your core (in `distance_unit`) |
| `break_point` | Collapse when strength falls below (1 - break_point) x peak |
| `posture` | `attack` or `defend` (a defender gets its terrain bonus at the start line) |
| `tempo` | Speed multiplier on the front when this side is the one gaining ground (offensive doctrine >1, defensive <1) |

## How the model works (for explaining results)

Each turn: air and sea control set combat multipliers; each side's effective power is
strength x quality x training x morale x supply x air x sea x C2 x terrain; losses follow a
noisy Lanchester square law; the front moves toward the weaker side; morale, reserves and
replacements update. A side loses when its core is overrun, its army breaks, or its morale
collapses. Otherwise the run is a stalemate at the turn limit or ceasefire.

Sensitivity: each uncertain input is split into top and bottom thirds across the runs (events:
happened vs not) and the win-rate difference is reported, with a two-standard-error test to
flag noise.

## Ground rules

- Keep it abstract and hobbyist: force-level numbers from public sources only. Don't add
  operational detail such as real unit locations, targeting or tactics.
- For hypothetical modern matchups between real countries, note that the scenario is a
  thought experiment, not a prediction or a statement about intentions.
- Calibrate historical scenarios loosely against what happened (e.g. Germany should lose
  most runs from June 1941) and say what the model leaves out.
