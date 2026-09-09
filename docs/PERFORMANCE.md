# Tier 3 — skill quality, reliability, cost and time

The deterministic tier asks whether the plumbing still emits the same bytes.
This tier asks the four questions a release actually turns on:

> Did the skills get **less reliable**, **worse**, **more expensive**, or
> **slower**?

Nothing in tiers 1 and 2 answers any of them. `METHODOLOGY.md` used to list all
four as out of scope; this tier is what changed that, and that file now points
here.

## Why the deterministic tier cannot answer them

Every tier-1 expectation is a recorded byte string. A release that made every
skill twice as slow, three times as expensive, and worse at routing would match
all 337 of them and print **PASSED**. That is not a defect in tier 1 — pinning
contracts is what it is for — but it means a green tier-1 run is evidence about
*contracts*, never about *skills*.

## The two halves

| | `runner/measure_skills.py` | `runner/perf_gate.py` |
|---|---|---|
| What it does | Runs the controlled scenario set against a build | Judges a measurement against a baseline |
| Needs | `claude`, network, money | Nothing — stdlib, offline |
| Output | `results/measurements.json` | a verdict, and `results/perf.json` |

Split for the same reason tier 1 splits recording from comparing: a measurement
bought once can be re-judged under new thresholds without paying again.

## What is measured, and from where

**Reliability** — routing accuracy per skill (does a natural request reach the
right skill, and do `disable-model-invocation` skills stay silent), and whether
pipeline runs reach a completed status at all.

**Cost** — `cost_usd` per run. For pipeline scenarios this comes from acs's own
ledger, `<ticket>/<skill>-state.json`, which is the same document `/acs:usage`
bills from — so the evaluation and the product cannot disagree about what a run
cost. `role_usage` is carried through, so a cost rise can be attributed to the
planner, executor, verifier or coordinator rather than just observed.

**Time** — wall clock, measured by the collector rather than read from the
ledger, because the ledger's own timing is part of what is under test.

**Quality** — verify iterations to pass, achieved coverage against the repo's
configured target, and whether a run finished carrying an unresolved blocking
finding. Iterations-to-pass is the closest thing the pipeline records to a
quality measure: it counts how often the executor's first answer was not good
enough, and it costs money on every ticket.

Routing probes record **no cost**. The session is killed at the first `Skill`
tool_use — that is what keeps a probe to time-to-route instead of a whole skill
body — so it never emits a cost envelope. `cost_usd` is `null` rather than
estimated; an invented number in a cost baseline is worse than an absent one.

## The decision rules

Stated here because `METHODOLOGY.md` is right that `runs: 3` with no declared
rule is not a criterion.

- **Routing, positive probe** — passes only if it routes to the expected skill
  on **every** run. A split result is a finding, never a pass. Routing is
  stochastic; one green run is not evidence.
- **Routing, negative probe** — passes only if the skill auto-invokes on **no**
  run. This is the `disable-model-invocation` guarantee, and it is the one
  `critical` in this tier.
- **Cost, time, iterations, coverage** — compared as the **median** across
  runs, never a single run, so one timeout cannot move the number a release is
  judged on. The min/max spread is recorded alongside, because that spread is
  what calibration reads.

## Absolute gates block; relative gates are opinions until calibrated

This is the part that keeps the tier honest.

**Absolute** gates — routing accuracy, run completion, unresolved blocking
findings — are definitions, not measurements. A positive probe that routes on
four runs of five is unreliable whatever any baseline says. These block on the
very first measurement, with no baseline needed.

**Relative** gates — cost, time, verify iterations, coverage — are ratios
against a recorded baseline. A ratio nobody has calibrated against observed
noise is an opinion, and an opinion that blocks releases trains people to
override the gate. So while `dataset/thresholds.json` carries
`basis: provisional`, relative findings are **reported and never block**. The
verdict for that state is `PASSED (uncalibrated drift)` — a prompt to look, not
a claim of a defect.

`calibration_protocol` in that file is how they stop being provisional: run
`make measure` repeatedly against one unchanged build, and the spread that
produces is the tier's noise floor. Set each ratio outside it with margin,
record the measurement in `calibrated_from`, and set `basis` to `calibrated`.
A threshold tighter than the noise floor makes the gate a random number
generator; one far looser makes it decorative.

## The verdicts

| State | Condition |
|---|---|
| **UNMEASURED** | No measurement exists. Exit non-zero. |
| **BLOCKED (critical)** | A `disable-model-invocation` skill auto-invoked. |
| **BLOCKED** | An absolute floor was crossed. |
| **UNCOMPARED (baseline established)** | Floors held; first measurement for this scenario set, so nothing to compare. |
| **PASSED (uncalibrated drift)** | A provisional relative threshold was crossed. Look, do not block. |
| **PASSED** | Floors held and no axis regressed past its threshold. |

**UNMEASURED is the default, and it fails.** Absence is not a pass. The failure
mode this whole tier exists to fix is a green report that quietly means less
than a reader thinks, so it may never be green by having run nothing.

## Cost of the tier itself

`make measure-plan` prints it before anything is spent. At the shipped scenario
set that is **144 sessions**: 27 routing probes × 5 runs (each a few seconds,
killed at the first `Skill` call) plus 3 pipeline scenarios × 3 runs (one of
which is a full `/acs:code` TDD cycle). `make measure-routing` runs the cheap
half alone.

The pipeline set is deliberately three scenarios, not twenty-five.
`scenarios.json` names every skill it excludes and why, so the gap is
reviewable rather than merely absent.

## Status and limitations

**No measurement of acs has been taken yet.** `dataset/baselines/` is empty and
the thresholds are provisional. What is verified today is the comparator: 22
cases in `runner/test_perf_gate.py` assert the decision rules hold against
synthetic records. Those records test the arithmetic and the rules and say
**nothing whatever** about acs.

Known limitations, worst first:

1. **The scenario set is a sample of three pipeline runs.** Cost and quality
   findings generalise to the surfaces those three touch and no further.
2. **Sandbox runs are not consumer runs.** The scenarios use a throwaway repo
   with a trivial change. Real tickets are larger, and a cost baseline taken
   here understates real spend — it is useful for *deltas between releases*,
   not as an estimate of what a consumer pays.
3. **Model changes confound build changes.** A cost or quality delta can come
   from the model behind `claude`, not from acs. `environment` records the CLI
   version for exactly this reason, and a delta across a model change should be
   re-baselined rather than triaged as a regression.
4. **Three runs is a small n.** Enough to satisfy the routing rule (which needs
   unanimity, not a mean), thin for medians on cost and time. Raise
   `runs_per_scenario` when the budget allows; the spread in each record says
   whether it needs raising.
