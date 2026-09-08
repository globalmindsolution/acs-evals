# Release checklist — cutting an `acs` version

The evaluation steps that belong in an `acs` release cut, in order. Full
process and triage rules: [`EVALUATION-PROCESS.md`](EVALUATION-PROCESS.md).

Copy this into the release PR and tick it.

## Before the version bump

- [ ] **Working tree is green.** The code being released behaves as recorded.

      ```bash
      export ACS_PLUGIN_ROOT=~/src/gms-marketplace/plugins/acs
      make gate
      ```

- [ ] **Every failure is resolved**, each to one of the three outcomes —
      regression fixed, golden re-recorded in its own reviewed commit, or case
      corrected as a dataset bug. No case is left red.

- [ ] **Every known divergence has a decision.** Read the report's *Known
      divergences* section. For each: fixed in this release, or accepted and
      named in the changelog. An undecided divergence blocks the cut.

- [ ] **New surfaces have cases.** Anything in this release's changelog that
      added an observable surface — a CLI subcommand, a schema, a gate, a
      skill — has at least one case pinning it. If not, add it now; that is
      cheaper than finding out from a consumer.

- [ ] **The generated eval tree is in sync** (`make check`, included in
      `make gate`).

## At the version bump

- [ ] **Re-baseline the dataset.** Set `recorded_against` in
      `dataset/manifest.json` to the version being released, and clear
      `recorded_against_note` if it no longer applies. Otherwise every later
      run prints an off-baseline warning and the gate's verdict softens to
      "PASSED (off-baseline)".

- [ ] **Bump `dataset_version`** if cases changed in this cycle. Patch for
      added cases, minor for a changed case format, major for a runner
      contract change.

- [ ] **Re-run the gate** after re-baselining, so the committed report matches
      the released version.

## After publishing

- [ ] **Install the published build and run the gate against it** — with
      `ACS_PLUGIN_ROOT` **unset**, so the runner resolves the installed
      plugin rather than the source tree:

      ```bash
      claude plugin install acs@gms-marketplace
      unset ACS_PLUGIN_ROOT
      make gate
      ```

      This is the only step that catches **packaging drift** — a file that
      exists in the source tree but never reaches the published plugin. A
      source-tree run cannot see it.

- [ ] **Attach `results/report.md`** to the release PR or the GitHub release
      notes.

- [ ] **Tag the dataset** at the state that gated this release, so the
      evidence is recoverable later:

      ```bash
      git tag -a acs-v0.4.10-gate -m "Dataset state that gated acs v0.4.10"
      git push origin acs-v0.4.10-gate
      ```

## Not covered by this checklist

Runtime skill routing. The `evals/` tier that would verify it has never been
executed — see the last section of
[`EVALUATION-PROCESS.md`](EVALUATION-PROCESS.md). Do not record routing as
verified in release notes on the strength of this gate alone.
