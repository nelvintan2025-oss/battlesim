# Hypothetical: Singapore vs Malaysia (modern conventional): simulation report

> Simplified abstract model for hobbyist what-if exploration, built on public open-source estimates. Not a forecast. Treat the numbers as *relative*, not literal.

A purely hypothetical short, high-intensity conventional conflict, for hobbyist what-if exploration only. The two countries are close partners (ASEAN, the Five Power Defence Arrangements) and no such conflict is expected. One turn is one day; the limit is 60 days, and outside pressure for a ceasefire is likely. Strength is in thousands of combat-equivalent troops; air and naval are indices of modern platforms x quality x support (AEW, tankers, ISR). A side loses if the front is pushed past its depth: Singapore has almost none (roughly 10 to 20 km of urban island), Malaysia's southern core is deeper (60 to 120 km of Johor).

## Headline (1000 runs)

- **Singapore**: 41% (±3 pts, median 18 days)
- **Malaysia**: 10% (±2 pts, median 5 days)
- **Stalemate / ceasefire**: 49% (±3 pts, median 11 days)

## How the wars ended

- No decision (ceasefire imposed): 486 runs (49%)
- Singapore wins, Malaysia's morale / political collapse: 414 runs (41%)
- Malaysia wins, Singapore's morale / political collapse: 91 runs (9%)
- No decision (turn limit): 5 runs (0%)
- Malaysia wins, Singapore's core territory overrun: 4 runs (0%)

In the 491 undecided runs the front ended inside Malaysia in 478, inside Singapore in 11, and near the start line in 2.

## What decides it

Ranked by how much the outcome swings between the top and bottom third of each uncertain factor (or whether an event happens).

| Factor | When high / it happens | When low / it doesn't | Effect |
|---|---|---|---|
| Event: International ceasefire imposed | Singapore 7% · Malaysia 10% | Singapore 90% · Malaysia 9% | mostly denies Singapore a win; draws more likely (Singapore -82, Malaysia +1 pts) |
| Event: Malaysia achieves surprise | Singapore 25% · Malaysia 40% | Singapore 47% · Malaysia 0% | favours Malaysia (Singapore -22, Malaysia +40 pts) |
| Malaysia starting morale | Singapore 34% · Malaysia 10% | Singapore 50% · Malaysia 8% | mostly denies Singapore a win; draws more likely (Singapore -16, Malaysia +1 pts) |
| Malaysia strategic depth | Singapore 35% · Malaysia 10% | Singapore 47% · Malaysia 7% | mostly denies Singapore a win; draws more likely (Singapore -12, Malaysia +3 pts) |
| Event: Singapore achieves surprise | Singapore 42% · Malaysia 1% | Singapore 41% · Malaysia 12% | mostly denies Malaysia a win; draws more likely (Singapore +1, Malaysia -11 pts) |

Within the noise at this run count (no clear effect): Event: Outside power arms Malaysia mid-war, Singapore air power, Singapore home terrain advantage, Singapore starting morale, Malaysia training & leadership, Malaysia starting frontline strength, Malaysia logistics / supply, Singapore starting frontline strength, Singapore mobilisation speed, Malaysia mobilisable reserves, Malaysia command, control & ISR, Malaysia home terrain advantage.

## When does Singapore win?

Singapore wins 41% overall. Its odds move most when:

- *International ceasefire imposed* does not happen (90% vs 7%)
- *Malaysia achieves surprise* does not happen (47% vs 25%)
- Malaysia starting morale is low (50% vs 34%)
- Malaysia strategic depth is low (47% vs 35%)

## When does Malaysia win?

Malaysia wins 10% overall. Its odds move most when:

- *Malaysia achieves surprise* happens (40% vs 0%)
- *Singapore achieves surprise* does not happen (12% vs 1%)
- Singapore strategic depth is low (13% vs 6%)
- Malaysia equipment quality is high (12% vs 6%)
- Singapore starting morale is low (12% vs 7%)

## Caveats

- Lanchester-style attrition with multiplicative modifiers; no geography, no individual units, no diplomacy beyond the scripted events.
- Inputs are rough public estimates with wide ranges; change them with `--set` and see how fragile each conclusion is.
- 'Drivers' are correlations inside this model, not proof of real-world causation.

## Public sources behind the inputs

- IISS, The Military Balance 2024/2025 (active and reserve personnel: Singapore ~51,000 active / ~250,000 reserve; Malaysia ~113,000 active / ~51,600 reserve)
- SIPRI Military Expenditure Database (defence budgets: Singapore ~US$13bn, Malaysia ~US$4bn, 2023-24)
- Public fleet listings (Wikipedia / official sites): RSAF F-15SG and F-16, G550 AEW, A330 MRTT; RMAF Su-30MKM, F/A-18D, Hawk, FA-50 on order; RSN Formidable-class frigates and submarines; RMN Lekiu and Kedah classes, Scorpene submarines
- Commentary on Singapore's forward-defence doctrine, water dependence on Johor, and lack of strategic depth (open-source analysis, e.g. RSIS and Lowy Institute pieces)
