#!/usr/bin/env python3
"""Tier 3's collector: run the controlled scenario set and record what it cost.

This is the half that needs a real `claude`, real network, and real money. It
produces `results/measurements.json`; `runner/perf_gate.py` is what judges it,
and that half is pure. The split is deliberate and matches tier 1's: recording
and judging are two acts, so a measurement taken once can be re-judged under
new thresholds without paying for it again.

    python3 runner/measure_skills.py --dry-run        # the plan, no spending
    python3 runner/measure_skills.py --routing-only   # cheap tier: 27 probes
    python3 runner/measure_skills.py                  # everything

Two measurement notes that decide how the numbers may be read:

* **Routing probes record time, not cost.** The process is killed the instant
  the first `Skill` tool_use appears — that is what keeps a routing probe to
  time-to-route instead of a whole skill body — and killing it means the
  session never emits its cost envelope. `cost_usd` is recorded as null rather
  than estimated, because an invented number in a cost baseline is worse than
  an absent one.
* **Pipeline cost and quality come from acs's own ledger**, not from this
  script's observations: `<ticket>/<skill>-state.json` is what `/acs:usage`
  reads, so the evaluation and the product cannot disagree about what a run
  cost. Wall clock is measured here because the ledger's own timing is what is
  under test.
"""

import argparse
import datetime
import json
import os
import shutil
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from harness import DATASET, BuildError, Sandbox, resolve_build  # noqa: E402
from perf_gate import summarize  # noqa: E402

SCENARIOS = os.path.join(DATASET, "scenarios.json")
ROUTING = os.path.join(DATASET, "routing.json")

PIPELINE_TOOLS = ("Bash", "Read", "Write", "Edit", "Glob", "Grep", "Task",
                  "TodoWrite", "Skill")


# --------------------------------------------------------------------------
# Driving claude
# --------------------------------------------------------------------------

def route_once(prompt, cwd, timeout, env):
    """Return (routed_to, seconds). Killed at the first Skill call.

    `routed_to` is None when the model stopped, or the timeout elapsed, without
    invoking any skill — which for a negative probe is the passing outcome, so
    None is a result here and never an error.
    """
    cmd = ["claude", "-p", prompt, "--output-format", "stream-json",
           "--verbose", "--permission-mode", "acceptEdits",
           "--allowedTools", "Skill"]
    started = time.time()
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE,
                            stderr=subprocess.DEVNULL, text=True,
                            cwd=cwd, env=env)
    routed = None
    deadline = started + timeout
    try:
        for line in proc.stdout:
            if time.time() > deadline:
                break
            try:
                event = json.loads(line)
            except (json.JSONDecodeError, TypeError):
                continue
            if event.get("type") != "assistant":
                continue
            for block in (event.get("message") or {}).get("content") or []:
                if block.get("type") == "tool_use" and block.get("name") == "Skill":
                    routed = (block.get("input") or {}).get("skill")
                    break
            if routed:
                break
    finally:
        proc.kill()
        proc.wait()
        if proc.stdout:
            proc.stdout.close()
    return routed, round(time.time() - started, 3)


def session_once(prompt, cwd, timeout, env):
    """One full `claude -p` session. Returns the envelope plus wall clock."""
    cmd = ["claude", "-p", prompt, "--output-format", "json",
           "--permission-mode", "acceptEdits",
           "--allowedTools", " ".join(PIPELINE_TOOLS)]
    started = time.time()
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, cwd=cwd,
                              timeout=timeout, env=env)
    except subprocess.TimeoutExpired:
        return {"ok": False, "seconds": round(time.time() - started, 3),
                "cost_usd": None, "turns": None, "error": "timeout"}
    out = {"ok": proc.returncode == 0, "seconds": round(time.time() - started, 3),
           "cost_usd": None, "turns": None, "error": None}
    try:
        env_doc = json.loads(proc.stdout)
        out["cost_usd"] = env_doc.get("total_cost_usd")
        out["turns"] = env_doc.get("num_turns")
        out["ok"] = proc.returncode == 0 and not env_doc.get("is_error")
        if env_doc.get("is_error"):
            out["error"] = "session reported is_error"
    except (json.JSONDecodeError, TypeError):
        out["ok"] = False
        out["error"] = "unparseable session envelope"
    return out


# --------------------------------------------------------------------------
# Reading acs's own ledger
# --------------------------------------------------------------------------

def read_ledger(sandbox, skill):
    """The quality, cost and reliability signals acs recorded for itself.

    Returns the fields tier 3 compares. Every one is optional: a run that died
    early leaves no ledger, and `None` is the honest answer for a signal that
    was never written. It must never read as a zero — a zero coverage or zero
    iteration count would be a finding, and "we don't know" is not a finding.
    """
    out = {"status": None, "stop_reason": None, "ledger_cost_usd": None,
           "role_usage": [], "quality": {
               "verify_iterations": None, "coverage_percent": None,
               "coverage_target": None, "blocking_findings": None,
               "tests_passed": None}}
    tdir = sandbox.ticket_dir()
    path = os.path.join(tdir, "%s-state.json" % skill.split(":")[-1])
    if not os.path.exists(path):
        return out
    try:
        with open(path) as fh:
            doc = json.load(fh)
    except (OSError, json.JSONDecodeError):
        return out

    runs = doc.get("runs") or []
    if runs:
        last = runs[-1]
        out["status"] = last.get("status")
        out["stop_reason"] = last.get("stop_reason")
        out["ledger_cost_usd"] = last.get("cost_usd")
        out["role_usage"] = last.get("role_usage") or []

    states = doc.get("states") or {}
    review = states.get("review") or {}
    if isinstance(review.get("iterations"), int):
        out["quality"]["verify_iterations"] = review["iterations"]
    tests = states.get("tests") or {}
    if isinstance(tests.get("coverage_percent"), (int, float)):
        out["quality"]["coverage_percent"] = float(tests["coverage_percent"])
    if isinstance(tests.get("coverage_target"), (int, float)):
        out["quality"]["coverage_target"] = float(tests["coverage_target"])
    if isinstance(tests.get("passed"), bool):
        out["quality"]["tests_passed"] = tests["passed"]

    findings = doc.get("findings") or []
    if isinstance(findings, list):
        out["quality"]["blocking_findings"] = len(
            [f for f in findings
             if isinstance(f, dict) and f.get("severity") == "blocking"])
    return out


# --------------------------------------------------------------------------
# The run
# --------------------------------------------------------------------------

def measure_routing(build, scenarios, probes, env, limit=None):
    conf = scenarios["routing"]
    runs_per = limit or conf.get("runs_per_probe", 5)
    timeout = conf.get("timeout_seconds", 120)
    out = []
    with Sandbox(build, profile="ticketed") as sb:
        for probe in probes:
            runs = []
            for _ in range(runs_per):
                routed, seconds = route_once(probe["prompt"], sb.repo,
                                             timeout, env)
                runs.append({"ok": True, "routed_to": routed,
                             "seconds": seconds, "cost_usd": None,
                             "turns": None})
            rec = {"id": probe["id"], "kind": "routing",
                   "skill": probe["skill"],
                   "expect": {"must_route": probe.get("must_route", True),
                              "skill": probe["skill"]},
                   "runs": runs}
            rec["aggregate"] = summarize(rec)
            hits = rec["aggregate"]["reliability"]
            print("  %-32s %d/%d  %.1fs median"
                  % (probe["id"], hits["hits"], hits["total"],
                     rec["aggregate"]["seconds"]["median"]))
            out.append(rec)
    return out


def measure_pipeline(build, scenarios, env, limit=None):
    conf = scenarios["pipeline"]
    runs_per = limit or conf.get("runs_per_scenario", 3)
    out = []
    for scenario in conf["scenarios"]:
        runs = []
        for _ in range(runs_per):
            # A fresh sandbox per run: a second run reusing the first's
            # partition would measure resumption, not the skill.
            with Sandbox(build, profile=scenario["profile"]) as sb:
                prompt = scenario["prompt"]
                if sb.ticket_id:
                    prompt = prompt.replace("TKT-1", sb.ticket_id)
                run = session_once(prompt, sb.repo,
                                   scenario.get("timeout_seconds", 1800), env)
                ledger = read_ledger(sb, scenario["skill"])
            run["status"] = ledger["status"]
            run["stop_reason"] = ledger["stop_reason"]
            run["role_usage"] = ledger["role_usage"]
            run["quality"] = ledger["quality"]
            # The ledger is authoritative on cost when it has an opinion: it
            # is what /acs:usage bills the consumer from.
            if ledger["ledger_cost_usd"] is not None:
                run["cost_usd"] = ledger["ledger_cost_usd"]
            runs.append(run)
        rec = {"id": scenario["id"], "kind": "pipeline",
               "skill": scenario["skill"], "runs": runs}
        rec["aggregate"] = summarize(rec)
        agg = rec["aggregate"]
        print("  %-32s %d/%d completed  %s median"
              % (scenario["id"], agg["reliability"]["hits"],
                 agg["reliability"]["total"],
                 ("$%.2f" % agg["cost_usd"]["median"])
                 if agg["cost_usd"] else "cost n/a"))
        out.append(rec)
    return out


def claude_version():
    if not shutil.which("claude"):
        return None
    try:
        proc = subprocess.run(["claude", "--version"], capture_output=True,
                              text=True, timeout=30)
        return proc.stdout.strip() or None
    except (OSError, subprocess.SubprocessError):
        return None


def plan(scenarios, probes, routing_only, pipeline_only, limit):
    """What a run would cost, in sessions. Printed before anything is spent."""
    lines, sessions = [], 0
    if not pipeline_only:
        n = limit or scenarios["routing"].get("runs_per_probe", 5)
        lines.append("  routing   %d probes x %d runs = %d sessions "
                     "(killed at first Skill call)" % (len(probes), n,
                                                       len(probes) * n))
        sessions += len(probes) * n
    if not routing_only:
        n = limit or scenarios["pipeline"].get("runs_per_scenario", 3)
        for s in scenarios["pipeline"]["scenarios"]:
            lines.append("  pipeline  %-22s x %d runs, up to %ds each"
                         % (s["id"], n, s.get("timeout_seconds", 1800)))
            sessions += n
    lines.append("  TOTAL     %d claude sessions" % sessions)
    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser(
        description="tier 3 — measure skill quality, reliability, cost, time")
    ap.add_argument("--out", default="results/measurements.json")
    ap.add_argument("--dry-run", action="store_true",
                    help="print the plan and spend nothing")
    ap.add_argument("--routing-only", action="store_true")
    ap.add_argument("--pipeline-only", action="store_true")
    ap.add_argument("--runs", type=int, default=None,
                    help="override runs per probe (1 is cheap and NOISY — a "
                         "single run cannot satisfy the routing decision rule)")
    ap.add_argument("--probe", default=None, help="glob-filter routing probes")
    args = ap.parse_args()

    with open(SCENARIOS) as fh:
        scenarios = json.load(fh)
    with open(ROUTING) as fh:
        probes = json.load(fh)["probes"]
    if args.probe:
        import fnmatch
        probes = [p for p in probes if fnmatch.fnmatch(p["id"], args.probe)]

    print(plan(scenarios, probes, args.routing_only, args.pipeline_only,
               args.runs))
    if args.dry_run:
        print("\ndry run — nothing executed, nothing spent.")
        return 0

    if not shutil.which("claude"):
        sys.stderr.write(
            "\nerror: `claude` is not on PATH. Tier 3 measures real sessions; "
            "there is no offline mode.\n"
            "Use --dry-run to check the plan, or runner/perf_gate.py to "
            "re-judge a measurement you already have.\n")
        return 2

    try:
        build = resolve_build()
    except BuildError as exc:
        sys.stderr.write("error: %s\n" % exc)
        return 2

    env = dict(os.environ)
    print("\nbuild under test: acs %s\n" % build.version)
    started = time.time()
    records = []
    if not args.pipeline_only:
        records += measure_routing(build, scenarios, probes, env, args.runs)
    if not args.routing_only:
        records += measure_pipeline(build, scenarios, env, args.runs)

    # A partial measurement is marked, not silently promoted: a baseline built
    # from probes that half-ran would make every later comparison a lie.
    expected_routing = 0 if args.pipeline_only else len(probes)
    expected_pipeline = (0 if args.routing_only
                         else len(scenarios["pipeline"]["scenarios"]))
    incomplete = (len(records) != expected_routing + expected_pipeline
                  or any(r["aggregate"]["runs"] == 0 for r in records)
                  or args.routing_only or args.pipeline_only
                  or bool(args.probe))

    doc = {
        "schema": "acs-evals/measurement/1",
        "generated_at": datetime.datetime.now(datetime.timezone.utc)
                                .strftime("%Y-%m-%dT%H:%M:%SZ"),
        "build": {"version": build.version, "root": build.root},
        "scenario_set_version": scenarios["scenario_set_version"],
        "environment": {"claude_cli_version": claude_version(),
                        "host": sys.platform},
        "incomplete": incomplete,
        "probes": records,
    }
    directory = os.path.dirname(os.path.abspath(args.out))
    if directory:
        os.makedirs(directory, exist_ok=True)
    with open(args.out, "w") as fh:
        json.dump(doc, fh, indent=2)
        fh.write("\n")

    print("\nmeasurement written to %s  (%.1fs)"
          % (args.out, time.time() - started))
    if incomplete:
        print("marked INCOMPLETE — a partial measurement may not be promoted "
              "to a baseline.")
    print("judge it with: python3 runner/perf_gate.py --measurement %s"
          % args.out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
