# Baselines

One promoted measurement per gated release: `acs-<version>.json`, conforming to
[`../measurement.schema.json`](../measurement.schema.json). A run scoped to the
cheap half (`make measure-routing`) may be promoted as `acs-<version>-routing.json`
— the gate then compares routing probes against it and nothing else, says so
in its verdict, and a full `acs-<version>.json` supersedes it (it sorts later,
and `pick_baseline` takes the newest).

A baseline is not a separate artifact — it is `results/measurements.json` from a
run that was reviewed and kept, exactly as `reports/` holds a promoted report.

Promote one only when all three hold:

- the measurement is **not** marked `incomplete` — it finished what its
  `scope` set out to measure (a probe filter, or a probe with no runs, marks it
  incomplete; a routing-only run that finished does not),
- its `scenario_set_version` matches the current `../scenarios.json` (a changed
  experiment makes older numbers incomparable, and `perf_gate.py` refuses to
  compare across the boundary rather than pretending),
- the run's findings were triaged — a baseline recorded from a build with a
  known regression bakes that regression in as the thing to beat.

**This directory is empty.** No tier-3 measurement of acs has been taken yet, so
every cost, time and quality number the gate could compare against does not yet
exist. `perf_gate.py` reports UNMEASURED rather than green — see
[`../../docs/PERFORMANCE.md`](../../docs/PERFORMANCE.md).
