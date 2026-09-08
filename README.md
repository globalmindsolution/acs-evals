# acs-evals — golden dataset for the `acs` plugin

The evaluation repo for the [`acs`](https://github.com/globalmindsolution/gms-marketplace)
Claude Code plugin. It holds a **golden dataset**: a curated, versioned corpus
of inputs paired with the outputs the plugin actually produced, so a release can
be checked against recorded behaviour instead of against someone's memory of it.

Built as the release gate for **v0.4.10**.

## Why this exists, and how it differs from the plugin's own tests

The plugin repo already has two layers: `tests/` (unit tests, driving Python
functions directly) and `evals/` (behavioural scenarios that spawn `claude -p`).
This repo is a third thing, and the difference is what makes it useful:

- `tests/` asserts that a **function** does what its author intended.
- This dataset asserts that a **shipped build's observable surface** — exit
  codes, JSON documents, refusal messages, schemas, skill frontmatter — has not
  moved since the last release, whoever changed what underneath.

It runs against the **installed plugin** by default, not a source tree, so it
also catches packaging drift that a source-tree test suite cannot see.

## The evaluation process

One command runs the gate:

```bash
export ACS_PLUGIN_ROOT=~/src/gms-marketplace/plugins/acs   # the build being released
make gate
```

`make gate` = **`eval`** (run the 337 deterministic cases) → **`check`**
(assert both generated trees are in sync with their sources) → **`mutation`**
(measure schema coverage, floor 50%) → **`report`** (render
`results/report.md` and `results/report.html`). It stops at the first failure.

```
make help      every target
make eval      run the deterministic tier, write results/latest.json
make generate  re-render the two generated case trees
make mutation  measure schema coverage by deleting each constraint
make report    render the report from the last run
make list      list every case, run nothing
make record    DANGER — rewrite goldens from this build; read the diff
```

| Document | What it covers |
|---|---|
| [`docs/RUBRIC.md`](docs/RUBRIC.md) | **What a case is worth and what makes a run pass** — severity levels and release thresholds |
| [`docs/METHODOLOGY.md`](docs/METHODOLOGY.md) | Intended use, sampling, and the threats to validity — read before quoting a green run |
| [`docs/EVALUATION-PROCESS.md`](docs/EVALUATION-PROCESS.md) | Roles, when to run, how to triage a red case, re-recording rules, how to extend the dataset |
| [`docs/RELEASE-CHECKLIST.md`](docs/RELEASE-CHECKLIST.md) | The eval steps of an `acs` release cut, in order |
| [`reports/`](reports/) | The reviewed report for each gated release |

Not every case counts the same. Per [`docs/RUBRIC.md`](docs/RUBRIC.md), one
**critical** failure blocks a release outright, **major** blocks unless the
golden is re-recorded deliberately, and **minor** drift is triage rather than a
hold — so `make gate` exits non-zero on the first two and zero on the third.

Latest report: [`reports/acs-v0.4.10-gate.md`](reports/acs-v0.4.10-gate.md) —
**337/337 passed**, 2 known divergences, against acs `0.4.9` (the pre-`v0.4.10`
unreleased tree).

Run it **both ways** before a release. With `ACS_PLUGIN_ROOT` set you are
checking the code; with it unset the runner resolves the newest *installed*
build, which is what a consumer actually executes — that run is the only one
that catches packaging drift.

## Two tiers

| Tier | Where | Runner | Cost | Status |
|---|---|---|---|---|
| **Deterministic** | `dataset/` | `runner/run_golden.py` | $0, no model, no network | **337 cases, all green** |
| **Agentic (routing)** | `evals/` | `claude plugin eval` | paid sessions | authored, **never executed** — see below |

### Tier 1 — deterministic (runs today)

```bash
python3 runner/run_golden.py                     # everything
python3 runner/run_golden.py --list              # list cases, run nothing
python3 runner/run_golden.py -v                  # show every diff
python3 runner/run_golden.py --case 'VERDICT-*'  # glob by case id
python3 runner/run_golden.py --covers MAR-527    # everything covering one ticket
python3 runner/run_golden.py --profile ticketed  # one sandbox profile
```

Exit status is 0 only when every selected case matches. Stdlib only, Python
≥ 3.9 — the same constraint the plugin itself keeps.

**Which build gets tested.** `ACS_PLUGIN_ROOT` wins if set; otherwise the newest
installed build under `~/.claude/plugins/cache/*/acs/*/`; otherwise a
marketplace checkout under `~/.claude/plugins/marketplaces/*/plugins/acs`. The
banner prints what it resolved, and warns when the build's version differs from
the one the goldens were recorded against.

```bash
ACS_PLUGIN_ROOT=~/src/gms-marketplace/plugins/acs python3 runner/run_golden.py
```

### Tier 2 — agentic routing (not yet runnable)

`evals/routing/**/case.yaml` holds one probe per skill in Claude Code's official
`claude plugin eval` format. **None of it has been executed.** `plugin eval` is
early access and was not enabled on the account this dataset was built with, so
the case and grader schema is authored from `claude plugin eval --help`
(Claude Code 2.1.263) rather than from a passing run. Confirm the shape before
trusting a result:

```bash
claude plugin eval acs --case route-code --runs 1
```

The curated data lives in `dataset/routing.json`; the YAML is **generated**:

```bash
python3 runner/gen_plugin_eval.py           # render evals/routing/**/case.yaml
python3 runner/gen_plugin_eval.py --check   # fail if the tree is stale
```

Edit the JSON, never the generated YAML.

The half of routing that *is* checkable without a model — that all 25 skills
ship, carry a routing `description`, and declare the right
`disable-model-invocation` — is pinned deterministically in tier 1 as
`SKILL-*`.

## What the dataset covers

337 deterministic cases across the surfaces v0.4.10 changed **and** the pipeline
spine every release depends on.

| Cases | Group | What it pins |
|---:|---|---|
| 32 | `01-derivation` | slug, the 12-cell lane matrix, lane ranks, stakes recommendation and the ratchet guard, docs fan-out batching |
| 18 | `02-readiness` | merge-pr's four readiness dimensions replayed from recorded `gh pr view` documents (MAR-524) |
| 15 | `03-verdict` | the verifier verdict's derived-`passed` invariant, completeness, freshness, lens merge (MAR-527) |
| 8 | `04-filemap` | the executor file map's declaration side and its accumulating union (MAR-529) |
| 7 | `05-lock` | lock staleness bases and the audited `force-unlock` (MAR-530) |
| 45 | `06-gates` | all 15 gated skills × 3 workspace states — the pipeline ordering, and the reason each refusal gives |
| 12 | `07-spine` | ticket minting, the fail-closed id counter, settings resolution, ticket read/write |
| 35 | `08-schemas` | the 12 shipped JSON schemas — the accept seeds, and the reject cases that carry judgement |
| 12 | `09-internals` | PR conventions, doc structure lint, status line, metrics aggregate, SessionEnd |
| 25 | `10-skills` | every skill's shipped routing surface |
| 128 | `11-schema-constraints` | **generated** — one reject case per reachable schema constraint |

Tickets covered: MAR-402, MAR-520 – MAR-530.

### The cases worth reading first

- **`VERDICT-002`** — a verdict claiming `passed: true` while carrying a
  blocking finding is refused. This is the defect MAR-527 exists to remove, and
  the single most important assertion in the dataset.
- **`VERDICT-004`** — the same invariant in the other direction: a failure with
  no blocking finding recorded is also refused.
- **`READY-018`** — a truncated PR recording blocks on all four dimensions.
  Reporting "ready" from a document that never carried the evidence would merge
  on no evidence.
- **`MINT-001`** — minting refuses in a partition that has never allocated,
  rather than restarting the id sequence at 1.
- **`LOCK-004`** — a lock with no readable timestamp is *not* stale. The safe
  answer is "do not steal it".
- **`STAKES-REC-003`** — the default high-stakes globs are repo-root anchored,
  so `src/auth/**` does **not** match `auth/**`. A real sharp edge for any repo
  that nests its auth code.

## How much this actually catches

A passing suite says nothing about how much it would notice. The schema tier is
measured, not asserted — every constraint in every shipped schema is deleted in
turn, and one whose deletion leaves the suite green is a hole:

```bash
make mutation                                    # the coverage table
python3 runner/mutation_sweep.py --holes         # every unpinned constraint
```

Current: **126/229 constraints (55.0%)**. It was 9.3% when the cases were all
hand-written, which is why `11-schema-constraints.json` is generated from the
schemas themselves. The 103 that remain are mostly branches under
`oneOf`/`anyOf`, where breaking one constraint leaves another branch matching,
so a single-constraint reject case would be unsound —
`python3 runner/gen_schema_cases.py --report` lists them with reasons.

The CLI tier has no automated equivalent (mutating it needs a writable copy of
the build and a subprocess run per mutation). Spot-checked by hand, 6 of 7
decision-table mutations were caught — including the verdict invariant, the
readiness fail-closed path, gate messages and skill flags.

## Known divergences

Cases tagged `known_divergence` pin behaviour that differs from what the code's
own contract states. They assert what the build **actually does**, so that
closing the gap shows up as a loud failure rather than passing unnoticed.

- **`VERDICT-009` / `VERDICT-014`** — `acs verdict show` does not enforce
  iteration or skill freshness. `validate_verdict` implements both checks, but
  this call site passes only `ticket_id`, so `--iteration 3` reports
  `ok: true, passed: true` for a document whose own `iteration` is 1.
  **Read-only:** the two call sites that decide anything — `acs_lib/derive.py`
  (`verifier_passed`, which `gate_create_pr` reads) and `acs_lib/lifecycle.py`
  (the SubagentStop hook) — both pass all three arguments, so no gate is
  bypassed. If v0.4.10 wires the two arguments through, flip both cases to
  expect exit 2.

## When a case fails

A failure is not automatically a bug — it is a **behaviour change that needs a
decision**. There are exactly three outcomes:

1. The build changed and that is **wrong** → regression. Fix the plugin, leave
   the golden alone.
2. The build changed and that is **intended** → re-record that case, in its own
   commit, naming the ticket that justifies it.
3. The build is right and the **case** was wrong → a dataset bug. Fix the case
   and say so.

```bash
python3 runner/run_golden.py -v --case VERDICT-009   # see exactly what differs
make record                                          # then, deliberately
git diff dataset/cases/                              # and read EVERY line
```

Never re-record to turn a red run green without reading the diff — that
converts the gate into a rubber stamp, and it will not catch the next
regression either. Full triage guidance:
[`docs/EVALUATION-PROCESS.md`](docs/EVALUATION-PROCESS.md).

## Layout

```
Makefile                 the process, as commands — `make help`
dataset/
  manifest.json          dataset version, target release, recorded-against build
  routing.json           curated routing probes (source for evals/)
  cases/*.json           the golden cases, grouped by surface
  fixtures/
    readiness/           18 recorded `gh pr view` documents
    verdict/             15 verdict documents, honest and malformed
    lock/                3 foreign-lock states
runner/
  run_golden.py          the deterministic runner
  harness.py             build resolution, sandbox profiles, redaction
  jsonschema_mini.py     stdlib JSON Schema subset validator
  gen_plugin_eval.py     renders routing.json into evals/
  report.py              renders a run result into report.md + report.html
evals/
  routing/**/case.yaml   generated `claude plugin eval` cases
docs/
  EVALUATION-PROCESS.md  roles, triage, re-recording, extending the dataset
  RELEASE-CHECKLIST.md   the eval steps of a release cut
reports/                 the reviewed report for each gated release
results/                 working output of a run (gitignored)
```

## Writing a case

A case names a surface, an invocation, and what that invocation produced:

```json
{
  "id": "LANE-003",
  "title": "high stakes lifts even a trivial change to STANDARD and full review",
  "invoke": {"argv": ["lane", "derive", "--size", "trivial", "--stakes", "high"]},
  "expect": {
    "exit_code": 0,
    "stdout_json": {"ceiling": 3, "depth": "full", "lane": "STANDARD", "rank": 2}
  }
}
```

**Sandbox profiles** (`"profile"`, default `bare`) — each case gets a fresh one,
because several mutate workspace state:

| Profile | Contents |
|---|---|
| `bare` | git repo + `.acs/settings.json`, no tickets |
| `seeded` | `bare` + a reconciled `counters.json`, so minting is allowed |
| `ticketed` | `seeded` + `TKT-1`, a small/low-stakes task |
| `epic` | `seeded` + `TKT-1`, a large/high-stakes epic with `needs_design` |

**Expectation keys** — `exit_code`, `stdout_json` (exact), `stdout_json_subset`
(recursive containment; lists still match element for element),
`stdout_contains` / `stderr_contains`, `stdout_excludes` / `stderr_excludes`.

**Other case kinds** — `"kind": "schema"` validates an instance against a
shipped schema (`expect.valid`, `expect.errors_contain`);
`"kind": "skill_manifest"` asserts a skill's shipped frontmatter.

**Tokens** — `{{repo}}`, `{{ws}}`, `{{ticket_dir}}`, `{{ticket}}` and
`{{fixture:<path>}}` expand in `argv`; `{{now}}` and `{{hours_ago:N}}` expand
inside seeded documents, so a fixture whose meaning depends on the clock (a
lock's staleness) keeps its *relationship* fixed rather than its timestamp.

**Redaction** — sandbox paths, checkout ids and timestamps are replaced with
`<REPO>`, `<WS>`, `<CHECKOUT_ID>` and `<TS>` before matching, so expectations
compare byte for byte across machines.

Assert on **artifacts, never on prose** — a case passes because the right JSON
exists with the right values, not because a model said the right thing.
