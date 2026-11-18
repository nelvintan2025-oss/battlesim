# WW2 Eastern Front: Germany vs USSR (from June 1941): simulation report

> Simplified abstract model for hobbyist what-if exploration, built on public open-source estimates. Not a forecast. Treat the numbers as *relative*, not literal.

Operation Barbarossa and what follows, abstracted. One turn is one week; the limit is about four years. Strength is in thousands of combat-equivalent troops; air is an index of sorties x quality. Germany wins by reaching the Moscow line or breaking the Red Army; the USSR wins by breaking the Wehrmacht or rolling the front back to Germany.

## Headline (1000 runs)

- **Germany**: 34% (±3 pts, median 27 weeks)
- **USSR**: 66% (±3 pts, median 65 weeks)
- **Stalemate / ceasefire**: 0% (±0 pts)

## How the wars ended

- USSR wins, Germany's morale / political collapse: 627 runs (63%)
- Germany wins, USSR's core territory overrun: 201 runs (20%)
- Germany wins, USSR's morale / political collapse: 138 runs (14%)
- USSR wins, Germany's army broken by losses: 34 runs (3%)

## What decides it

Ranked by how much the outcome swings between the top and bottom third of each uncertain factor (or whether an event happens).

| Factor | When high / it happens | When low / it doesn't | Effect |
|---|---|---|---|
| Event: Early, harsh winter | Germany 15% · USSR 85% | Germany 59% · USSR 41% | favours USSR (Germany -44, USSR +44 pts) |
| Germany supply reach | Germany 50% · USSR 50% | Germany 20% · USSR 80% | favours Germany (Germany +30, USSR -30 pts) |
| USSR strategic depth | Germany 21% · USSR 79% | Germany 44% · USSR 56% | favours USSR (Germany -23, USSR +23 pts) |
| Event: Japan attacks the USSR in Siberia | Germany 55% · USSR 45% | Germany 32% · USSR 68% | favours Germany (Germany +23, USSR -23 pts) |
| Germany logistics / supply | Germany 43% · USSR 57% | Germany 23% · USSR 77% | favours Germany (Germany +20, USSR -20 pts) |
| USSR command, control & ISR | Germany 26% · USSR 74% | Germany 45% · USSR 55% | favours USSR (Germany -19, USSR +19 pts) |
| USSR mobilisation speed | Germany 24% · USSR 76% | Germany 43% · USSR 57% | favours USSR (Germany -19, USSR +19 pts) |
| USSR air power | Germany 23% · USSR 77% | Germany 41% · USSR 59% | favours USSR (Germany -18, USSR +18 pts) |

Within the noise at this run count (no clear effect): Germany starting frontline strength, Germany industrial replacement, Germany morale fragility, Germany home terrain advantage, Event: Lend-Lease at scale, Germany mobilisable reserves, USSR supply reach, Germany starting morale, USSR industrial replacement, Event: Western Allies open a second front, Event: Soviet industry evacuated east in time.

## When does Germany win?

Germany wins 34% overall. Its odds move most when:

- *Early, harsh winter* does not happen (59% vs 15%)
- Germany supply reach is high (50% vs 20%)
- USSR strategic depth is low (44% vs 21%)
- *Japan attacks the USSR in Siberia* happens (55% vs 32%)
- Germany logistics / supply is high (43% vs 23%)

## When does USSR win?

USSR wins 66% overall. Its odds move most when:

- *Early, harsh winter* happens (85% vs 41%)
- Germany supply reach is low (80% vs 50%)
- USSR strategic depth is high (79% vs 56%)
- *Japan attacks the USSR in Siberia* does not happen (68% vs 45%)
- Germany logistics / supply is low (77% vs 57%)

## Caveats

- Lanchester-style attrition with multiplicative modifiers; no geography, no individual units, no diplomacy beyond the scripted events.
- Inputs are rough public estimates with wide ranges; change them with `--set` and see how fragile each conclusion is.
- 'Drivers' are correlations inside this model, not proof of real-world causation.

## Public sources behind the inputs

- Glantz & House, When Titans Clashed (force sizes June 1941: ~3.8M Axis vs ~2.7-2.9M Soviet in the western districts)
- Krivosheev, Soviet Casualties and Combat Losses in the Twentieth Century (Soviet losses, mobilisation)
- Overy, Russia's War; Tooze, The Wages of Destruction (industry, Lend-Lease, German replacement limits)
- Wikipedia: Operation Barbarossa, Lend-Lease, Evacuation of Soviet industry (aggregated public figures)
