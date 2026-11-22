# 06. Assumptions log (workflow: analysis-assumptions-log)

**Analysis:** cleaning, profiling and insight work on the 2026 lap data. **Date:** 2026-11-22. **Analyst:** Claude with the project author.
**Decision informed:** one-stop versus two-stop strategy per circuit (`beta > 12P / N^2`).
**Data sources:** FastF1 race laps for 20 rounds (19 kept), the hand-compiled Pirelli allocation table. **Population:** 2026 season only.

An assumption is **critical** when confidence is Low and impact if wrong is High; those need a validation plan before the result is delivered.
Status counts: open 9, tested 5, closed 2, accepted 2026-11-19 1, deferred 1.

| ID | Category | Assumption | Rationale | Confidence | Impact if wrong | Critical | Status |
|---|---|---|---|---|---|---|---|
| D1 | Data | FastF1 lap times are accurate where `IsAccurate` is true. | FastF1's own timing-integrity flag; 3 clean-eligible laps were flagged. | High | Low |  | open |
| D2 | Data | The first 56 laps of Mexico City are representative of the whole race. | The API returned nothing after lap 56; the author chose to use what exists. | Medium | Medium |  | accepted 2026-11-19 |
| D3 | Data | A C-number (C1 to C5) is the same tyre recipe at every race. | Pirelli names compounds by number; not verified for 2026. | Low | High | YES | open |
| D4 | Data | The hand-compiled allocation table is correct. | One source per row (Pirelli press release or formula1.com). | Medium | High |  | open |
| D5 | Data | Used sets behave like new sets for tyre wear (10% of laps are on used sets). | Used sets are kept; `FreshTyre` stays as a column. | Medium | Medium |  | open |
| B1 | Business logic | A race is dropped as wet only above 25% wet laps. | Default chosen without data; a few wet laps only need removing. | Low | Medium |  | tested |
| B2 | Business logic | The track stays damp for 3 laps after rain. | Chosen as a short buffer. | Low | Low |  | tested |
| B3 | Business logic | The lap after a safety car, VSC or yellow is not representative. | Cold tyres and a bunched field. | Medium | Low |  | tested |
| B4 | Business logic | A lap over 7% slower than its stint median is not tyre-limited. | Spins and off-track laps; 12 laps removed. | Medium | Low |  | tested |
| B5 | Business logic | A stint needs at least 5 clean laps to give a slope. | Too few points otherwise. | Medium | Medium |  | open |
| B6 | Business logic | Dirty-air laps stay in v1. | Author decision to keep v1 simple. | Low | Medium |  | deferred |
| B7 | Business logic | Circuits are labelled by host city; round 16 (FastF1 'Bahrain Grand Prix') is Kuala Lumpur. | One rule for all circuits; FastF1 places round 16 at Sepang. | High | Low |  | closed |
| B8 | Business logic | N = 71 for Mexico City in the threshold. | That is the scheduled and run distance. | High | Low |  | closed |
| B9 | Business logic | Equal stint splits are a fair basis for the closed-form threshold `12P / N^2`. | Gives a clean headline; real stints are unequal. | Medium | Medium |  | open |
| S1 | Statistical | Degradation is linear in tyre age. | Baseline model in the scope. | Medium | Medium |  | open |
| S2 | Statistical | Fuel burn and track evolution act the same at every circuit (one pooled race-lap effect of -0.037 s per lap). | Race data cannot separate the two. | Low | High | YES | open |
| S3 | Statistical | Tyre wear is identified because stints start at different race laps. | Inside one stint age and lap are perfectly collinear; variance inflation factors are 1.0 to 1.3 pooled. | Medium | High |  | open |
| S4 | Statistical | Laps inside a stint are independent. | They are not (autocorrelation, shared driver and car). | High | Medium |  | tested |

## Critical assumptions and validation plans

| ID | Assumption | Alternatives / validation |
|---|---|---|
| D3 | A C-number (C1 to C5) is the same tyre recipe at every race. | Test the circuit x compound interaction (H2); compare C3 across circuits; read Pirelli notes on recipe changes. |
| S2 | Fuel burn and track evolution act the same at every circuit (one pooled race-lap effect of -0.037 s per lap). | Fit circuit-specific race-lap slopes and compare; report the combined effect only. |

## Alternatives considered (business logic)
- Wet rule: drop every race with any rain (simpler, loses Zandvoort, Kuala Lumpur and Montreal) versus the 25% cutoff chosen.
- Restart laps: keep them (more data, cold-tyre bias) versus dropping the lap after a non-green lap (chosen).
- Compound labels: model by relative label (simple, but not comparable across circuits) versus C1 to C5 (chosen).

## Peer-review sign-off
Not signed: a reviewer other than the analyst, such as the project author, should sign the log.
