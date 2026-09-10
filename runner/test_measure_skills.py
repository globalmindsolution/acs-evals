#!/usr/bin/env python3
"""Self-test for the routing collector's decision rule (`classify`).

Pure: feeds synthetic stream-json lines, no `claude`, no network, no cost.
The rule under test is the one `docs/PERFORMANCE.md` states — a description
prompt is decided by the first `Skill` tool_use; an explicit `/acs:<skill>`
prompt is decided by the `init` event's `slash_commands`; an explicit probe
whose stream never reports a registration list is `unmeasured`, never a pass.
"""

import json
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from measure_skills import classify, explicit_skill  # noqa: E402
from perf_gate import summarize  # noqa: E402


def _init(commands=("acs:install-hooks", "acs:update", "acs:code"),
          with_list=True):
    event = {"type": "system", "subtype": "init", "session_id": "s"}
    if with_list:
        event["slash_commands"] = list(commands)
    return json.dumps(event)


def _assistant(*blocks):
    return json.dumps({"type": "assistant",
                       "message": {"content": list(blocks)}})


def _skill(name):
    return {"type": "tool_use", "name": "Skill", "input": {"skill": name}}


def _text(text):
    return {"type": "text", "text": text}


class ExplicitSkillTest(unittest.TestCase):
    def test_description_prompt_is_not_explicit(self):
        self.assertIsNone(explicit_skill("Set up the git hooks for this repo."))

    def test_slash_command_names_its_skill(self):
        self.assertEqual(explicit_skill("/acs:install-hooks"), "acs:install-hooks")
        self.assertEqual(explicit_skill("  /acs:update  "), "acs:update")

    def test_arguments_are_dropped(self):
        self.assertEqual(explicit_skill("/acs:code MAR-1"), "acs:code")

    def test_bare_slash_is_nothing(self):
        self.assertIsNone(explicit_skill("/"))
        self.assertIsNone(explicit_skill(""))
        self.assertIsNone(explicit_skill(None))


class DescriptionProbeTest(unittest.TestCase):
    PROMPT = "Implement ticket TKT-1 using the TDD cycle."

    def test_first_skill_tool_use_decides(self):
        lines = [_init(), _assistant(_text("Thinking."), _skill("acs:code")),
                 _assistant(_skill("acs:create-pr"))]
        self.assertEqual(classify(lines, self.PROMPT),
                         ("acs:code", "skill_tool_use"))

    def test_stops_reading_at_the_decision(self):
        seen = []

        def lines():
            for line in [_init(), _assistant(_skill("acs:code")),
                         _assistant(_skill("acs:create-pr"))]:
                seen.append(line)
                yield line

        classify(lines(), self.PROMPT)
        self.assertEqual(len(seen), 2)

    def test_no_skill_call_is_a_none_result(self):
        lines = [_init(), _assistant(_text("I cannot help with that."))]
        self.assertEqual(classify(lines, self.PROMPT), (None, "skill_tool_use"))

    def test_init_registration_never_decides_a_description_probe(self):
        # The model must choose; the CLI knowing the command is not routing.
        lines = [_init(), _assistant(_text("Done."))]
        self.assertEqual(classify(lines, self.PROMPT), (None, "skill_tool_use"))

    def test_garbage_lines_are_skipped(self):
        lines = ["not json", "[1,2]", "null", _assistant(_skill("acs:setup"))]
        self.assertEqual(classify(lines, self.PROMPT),
                         ("acs:setup", "skill_tool_use"))


class ExplicitProbeTest(unittest.TestCase):
    def test_registered_command_routes_at_init(self):
        lines = [_init(), _assistant(_text("Resolving repo roots."))]
        self.assertEqual(classify(lines, "/acs:install-hooks"),
                         ("acs:install-hooks", "registered"))

    def test_decided_before_any_model_turn(self):
        seen = []

        def lines():
            for line in [_init(), _assistant(_text("first turn"))]:
                seen.append(line)
                yield line

        classify(lines(), "/acs:update")
        self.assertEqual(len(seen), 1)

    def test_unregistered_command_is_a_miss(self):
        lines = [_init(commands=("acs:code",)), _assistant(_text("?"))]
        self.assertEqual(classify(lines, "/acs:install-hooks"),
                         (None, "registered"))

    def test_init_without_a_registration_list_is_unmeasured(self):
        lines = [_init(with_list=False), _assistant(_text("?"))]
        self.assertEqual(classify(lines, "/acs:install-hooks"),
                         (None, "unmeasured"))

    def test_no_init_at_all_is_unmeasured(self):
        lines = [_assistant(_text("?"))]
        self.assertEqual(classify(lines, "/acs:update"), (None, "unmeasured"))

    def test_exact_command_match_only(self):
        # A same-named command from another namespace is not this skill.
        lines = [_init(commands=("other:install-hooks", "install-hooks"))]
        self.assertEqual(classify(lines, "/acs:install-hooks"),
                         (None, "registered"))


class GateReadsDetectionHonestlyTest(unittest.TestCase):
    """`summarize` scores `routed_to` only; `detection` explains, never scores."""

    def _probe(self, runs):
        return {"id": "ROUTE-install-hooks-explicit", "kind": "routing",
                "skill": "acs:install-hooks",
                "expect": {"must_route": True, "skill": "acs:install-hooks",
                           "explicit": True},
                "runs": runs}

    def test_registered_runs_are_hits(self):
        runs = [{"ok": True, "routed_to": "acs:install-hooks",
                 "detection": "registered", "seconds": 4.0, "cost_usd": None,
                 "turns": None}] * 3
        self.assertEqual(summarize(self._probe(runs))["reliability"]["hits"], 3)

    def test_unmeasured_runs_are_misses(self):
        runs = [{"ok": True, "routed_to": None, "detection": "unmeasured",
                 "seconds": 4.0, "cost_usd": None, "turns": None}] * 3
        rel = summarize(self._probe(runs))["reliability"]
        self.assertEqual((rel["hits"], rel["total"]), (0, 3))


if __name__ == "__main__":
    unittest.main()
