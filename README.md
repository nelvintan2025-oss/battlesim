# battlesim

A what-if battle simulator for hobbyists. It is a simplified, abstract model built on public
open-source estimates (IISS Military Balance, SIPRI and similar). It is a thought experiment,
not a forecast or a statement about anyone's intentions.

## Interactive simulator (Singapore vs Malaysia, hypothetical)

**Live page:** https://nelvintan2025-oss.github.io/battlesim/

- Every input is a slider: personnel, reservists, aircraft, ships, supplies, economy, strategy.
  Defaults come from public counts, and judgement calls are marked as estimates.
- Each update runs hundreds of simulated wars and shows who wins, how wars end and what decides them.
- Day-by-day replay on a real map: six front sectors, moving unit markers, pincers and encirclements
  (pockets that hold out, break out or surrender), landings and special operations.
- A 3D view you can rotate, or stand on the ground and walk around.

Source lives in `web/`: `engine.js` (simulation), `geo.js` (map data), `template.html` (page).
Build the single-file page with:

```bash
python web/build.py        # writes web/sg_my_simulator.html
```

Pushing to `main` rebuilds and deploys the page to GitHub Pages
(`.github/workflows/pages.yml`).

## Command-line simulator (Python)

A simpler single-front model with charts and a written report.

```bash
pip install numpy matplotlib
python battlesim.py list
python battlesim.py run ww2_germany_ussr -n 1000 --seed 1 -o out/ww2
python battlesim.py run sg_my_modern -n 200 --set A.air=120
python battlesim.py sweep ww2_germany_ussr --param A.logistics --values 0.5,0.7,0.9,1.0
```

See `SKILL.md` for the scenario format and how the model works, and `examples/` for sample
outputs. To use it as a Claude skill, put this folder in `~/.claude/skills/battle-sim/`.
