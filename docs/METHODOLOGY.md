# Methodology and limitations

A datasheet for this dataset: what it is, how it was built, what it can and
cannot tell you, and where it is weakest. Read this before quoting a green run
as evidence of anything.

## Intended use

**In scope.** Deciding whether a given `acs` plugin build behaves the way the
last recorded build behaved, across the surfaces listed in the README — as a
release gate, and as a regression net during development.

**Out of scope, and not merely unmeasured:**

- **Whether acs's behaviour is *correct*.** Every expectation records what the
  plugin *did*, not what it *should* do. A case passing means "unchanged", never
  "right". Where a behaviour is known to contradict its own contract, it is
  pinned as a `known_divergence` and reported, precisely because the dataset
  cannot make that judgement itself.
- **Whether acs is useful, or produces good code.** Nothing here evaluates
  output quality.
- **Runtime skill routing.** See *Threats to validity* below.
- **Performance, cost, or token consumption.**

## How expectations were produced

Every expectation was **observed, not derived from reading source**. The build
was driven in a sandbox, the real output captured, redacted, and pinned. Where
a value was predicted from a contract first, it was then confirmed against a
real run before being committed.

Two groups are **generated** rather than authored:

| Group | Generated from | Regenerate with |
|---|---|---|
| `11-schema-constraints` | the shipped JSON schemas | `make generate` |
| `evals/routing` | `dataset/routing.json` | `make generate` |

`make check` fails if either drifts from its source, so a hand edit to a
generated file cannot survive unnoticed.

## Sampling and coverage

The dataset is **not** a random sample; it is a targeted selection:

1. Everything the v0.4.10 changelog changed (MAR-520 – MAR-530).
2. The pipeline spine every release depends on regardless of the changelog.
3. The packaged surfaces a source-tree test suite cannot see — skills, schemas.

Coverage of the schema tier is **measured, not asserted** — every constraint is
deleted in turn and the suite re-run:

```bash
make mutation                                # the current number
python3 runner/mutation_sweep.py --holes     # every constraint nothing pins
```

The CLI tier has **no automated equivalent**. Its coverage claim rests on a
hand-run spot check of seven decision-table mutations, six of which were caught.
That is evidence, not a measurement, and it should not be quoted as one.

## Threats to validity

Listed worst-first. Each is a real reason a green run could mislead you.

### 1. Generated schema cases are derived from the schemas they test

`11-schema-constraints.json` reads a schema, breaks one of its constraints, and
asserts the schema rejects the result. This is circular by construction: it can
detect a schema **changing**, but it can never detect a schema being **wrong**.
A schema that has always required the wrong field will be pinned, faithfully,
forever.

The hand-written cases in `08-schemas.json` are the counterweight — they encode
a human's view of what a constraint is *for* — but they are the minority.
Treat the generated tier as change-detection, not validation.

### 2. Routing is unverified at runtime

`evals/` has never been executed. `claude plugin eval` is early access and was
not enabled on the account this dataset was built with, so its case and grader
schema is authored from the CLI's `--help` output rather than a passing run.

What *is* verified is the routing **surface**: that all 25 skills ship, carry a
description, and declare the right `disable-model-invocation` (`SKILL-*`).
**Whether a real request reaches the right skill is currently pinned by
nothing.** Do not record routing as verified on the strength of this gate.

When the tier is enabled, its decision rule needs stating before results are
trusted. Routing is stochastic; `runs: 3` with no declared rule is not a
criterion. A reasonable one — a probe passes if it routes on **all** runs, and a
split result is a finding rather than a pass — should be written down and put in
`RUBRIC.md` at that point.

### 3. The baseline is a moving target

`recorded_against` in `dataset/manifest.json` names the build the goldens came
from. Run against a different build, "no regression" only means "no *unexpected*
change" — the report says so, but a reader skimming for green can miss it.

### 4. Single-observation goldens

Each deterministic case is recorded from **one** run. That is sound because the
tier is deterministic by construction (fixed sandbox, redacted clocks and
paths), but any surface that turned out to be non-deterministic would be pinned
to whichever value was observed first. The one place this bit us — a generator
expanding a clock token at build time — was caught by `make check`, not by the
suite.

### 5. Severity is a judgement

The levels in [`RUBRIC.md`](RUBRIC.md) were assigned by the dataset's author
against stated criteria, not derived from incident data. They are reviewable and
should be argued with; a case in the wrong band is a defect in the gate.

### 6. The harness and the dataset share an author

The same person wrote the cases and the runner that judges them, so a blind spot
in one is likely mirrored in the other. `mutation_sweep.py` exists to reduce
this — it asks whether the suite catches anything, independently of whether it
passes — but it covers only the schema tier.

## Independence

The dataset lives in a separate repository from the plugin deliberately: it
cannot be edited in the same change that alters the behaviour it pins, so
weakening a case and changing the code are two reviewable acts, not one.

The counterweight to that independence is drift — a plugin change that adds a
surface leaves this repo behind. The release checklist's "new surfaces have
cases" step is the only thing closing that loop, and it is a human step.

## Reproducibility

- Stdlib only, Python ≥ 3.9. No network, no model, no external services.
- One fresh sandbox per case: no case can see another's writes.
- Run-specific values (paths, checkout ids, timestamps, the build root) are
  redacted to stable tokens before matching.
- Time-relative fixtures use `{{now}}` / `{{hours_ago:N}}` so a lock's meaning
  stays fixed as the clock moves.
- Generation is deterministic and `make check`-verified.

A run is fully described by `results/latest.json`: the build, the dataset
version, the baseline, every case's status and severity, and the diffs.
