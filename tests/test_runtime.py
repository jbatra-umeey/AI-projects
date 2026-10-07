import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import patch

from agentloop.benchmark import benchmark
from agentloop.domain import Decision, STAGES
from agentloop.runtime import Runtime
from agentloop.store import Store
from agentloop.tools import TOOLS, Tool, TransientError


class FixedPlanner:
    def __init__(self, tool, arguments=None):
        self.tool = tool
        self.arguments = arguments or {}

    def decide(self, _):
        return Decision(self.tool, "Deliberately adversarial test decision.", self.arguments)


class RuntimeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = str(Path(self.temp.name) / "state.db")
        self.store = Store(self.path)
        self.runtime = Runtime(self.store)

    def complete(self, scenario="regression"):
        run = self.runtime.start("Investigate latency", scenario)
        run = self.runtime.run_until_pause(run.id)
        if run.status == "awaiting_approval":
            self.runtime.approve(run.id, True)
            run = self.runtime.run_until_pause(run.id)
        return run

    def test_full_loop_uses_all_nine_stages(self):
        run = self.complete()
        self.assertEqual("completed", run.status)
        self.assertEqual(set(STAGES), {e["stage"] for e in self.store.events(run.id)})
        self.assertEqual(140.0, run.result["latency_change_pct"])
        self.assertFalse(run.evidence["remediation"]["production_changed"])
        self.assertEqual("not_established", run.result["evaluation"]["causality"])

    def test_real_langgraph_feedback_edge(self):
        graph = self.runtime.graph.get_graph()
        self.assertIn("decide", graph.nodes)
        self.assertTrue(any(e.source == "next_action" and e.target == "restore_memory" for e in graph.edges))
        run = self.runtime.start("Investigate")
        run = self.runtime.run_until_pause(run.id)
        self.assertEqual(5, run.steps)
        self.assertEqual("awaiting_approval", run.status)

    def test_approval_survives_runtime_restart(self):
        run = self.runtime.start("Investigate")
        run = self.runtime.run_until_pause(run.id)
        self.assertNotIn("remediation", run.evidence)
        resumed = Runtime(Store(self.path))
        resumed.approve(run.id, True)
        result = resumed.run_until_pause(run.id)
        self.assertEqual("completed", result.status)
        self.assertEqual(1, result.attempts["simulate_remediation"])

    def test_checkpoint_resumes_without_repeating_successful_tools(self):
        run = self.runtime.start("Investigate")
        self.runtime.step(run.id)
        resumed = Runtime(Store(self.path))
        run = resumed.run_until_pause(run.id)
        self.assertEqual(1, run.attempts["query_metrics"])
        self.assertEqual(1, run.attempts["list_deployments"])

    def test_denial_never_executes_remediation(self):
        run = self.runtime.start("Investigate")
        self.runtime.run_until_pause(run.id)
        run = self.runtime.approve(run.id, False)
        self.assertEqual("cancelled", run.status)
        self.assertNotIn("simulate_remediation", run.attempts)
        self.assertEqual("cancelled", self.runtime.step(run.id).status)

    def test_duplicate_approval_is_rejected(self):
        run = self.runtime.start("Investigate")
        self.runtime.run_until_pause(run.id)
        self.runtime.approve(run.id, True)
        with self.assertRaises(ValueError):
            self.runtime.approve(run.id, True)
        self.assertEqual(1, self.store.get(run.id).attempts["simulate_remediation"])

    def test_concurrent_approvals_execute_once(self):
        run = self.runtime.start("Investigate")
        self.runtime.run_until_pause(run.id)
        def approve():
            try:
                self.runtime.approve(run.id, True)
                return "approved"
            except ValueError:
                return "rejected"
        with ThreadPoolExecutor(max_workers=2) as pool:
            outcomes = list(pool.map(lambda _: approve(), range(2)))
        self.assertCountEqual(["approved", "rejected"], outcomes)
        self.assertEqual(1, self.store.get(run.id).attempts["simulate_remediation"])

    def test_missing_evidence_escalates_and_does_not_enter_memory(self):
        run = self.complete("insufficient")
        self.assertEqual("blocked", run.status)
        self.assertFalse(run.result["evaluation"]["passed"])
        self.assertEqual([], self.store.memories("insufficient"))

    def test_successful_memory_is_revalidated(self):
        previous = self.complete()
        run = self.runtime.start("Recheck latency")
        self.assertEqual(previous.id, run.memories[0]["source_run"])
        self.assertEqual({}, run.evidence)
        run = self.runtime.step(run.id)
        self.assertIn("metrics", run.evidence)

    def test_transient_failure_retries_once(self):
        run = self.complete("transient")
        self.assertEqual("completed", run.status)
        self.assertEqual(2, run.attempts["query_metrics"])

    def test_repeated_transient_failure_stops(self):
        def unavailable(_):
            raise TransientError("Unavailable")
        with patch.dict(TOOLS, {"query_metrics": Tool("query_metrics", "test", "read", unavailable)}):
            run = self.runtime.start("Investigate")
            run = self.runtime.run_until_pause(run.id)
        self.assertEqual("failed", run.status)
        self.assertEqual(2, run.attempts["query_metrics"])

    def test_unknown_tool_is_blocked(self):
        runtime = Runtime(self.store, FixedPlanner("shell_exec"))
        run = runtime.start("Investigate")
        run = runtime.run_until_pause(run.id)
        self.assertEqual("blocked", run.status)
        self.assertEqual({}, run.attempts)

    def test_tool_arguments_cannot_smuggle_commands(self):
        runtime = Runtime(self.store, FixedPlanner("query_metrics", {"shell": "whoami"}))
        run = runtime.start("Investigate")
        run = runtime.run_until_pause(run.id)
        self.assertEqual("blocked", run.status)
        self.assertEqual({}, run.attempts)

    def test_early_remediation_is_blocked(self):
        runtime = Runtime(self.store, FixedPlanner("simulate_remediation"))
        run = runtime.start("Investigate")
        run = runtime.step(run.id)
        self.assertEqual("blocked", run.status)
        self.assertIsNone(run.pending)

    def test_premature_finish_fails_evidence_gate(self):
        runtime = Runtime(self.store, FixedPlanner("finish"))
        run = runtime.start("Investigate")
        run = runtime.step(run.id)
        self.assertEqual("blocked", run.status)
        self.assertFalse(run.result["evaluation"]["passed"])

    def test_budget_is_hard_limit(self):
        run = self.runtime.start("Investigate", max_steps=2)
        run = self.runtime.run_until_pause(run.id)
        self.assertEqual("budget_exhausted", run.status)
        self.assertEqual(2, run.steps)
        self.assertEqual(2, sum(run.attempts.values()))

    def test_terminal_step_is_idempotent(self):
        run = self.complete("healthy")
        before = self.runtime.snapshot(run.id)
        self.runtime.step(run.id)
        self.assertEqual(before, self.runtime.snapshot(run.id))

    def test_injection_text_does_not_authorize_tools(self):
        run = self.complete("injection")
        self.assertIn("shell_exec", run.evidence["runbook"]["text"])
        self.assertNotIn("shell_exec", run.attempts)
        # The independent unknown-tool test models an LLM obeying the injection.
        self.assertEqual("completed", run.status)

    def test_validation_rejects_bad_input(self):
        for fields in [{"goal": ""}, {"goal": "x", "max_steps": True},
                       {"goal": "x", "max_steps": 21}, {"goal": "x", "scenario": []},
                       {"goal": "x", "planner": "unsupported"}]:
            with self.subTest(fields=fields), self.assertRaises(ValueError):
                self.runtime.start(**fields)
        with self.assertRaises(ValueError):
            self.runtime.approve("unknown", "false")

    def test_trajectory_benchmark(self):
        result = benchmark()
        self.assertEqual(5, result["scenarios"])
        self.assertEqual(5, result["passed"])


if __name__ == "__main__":
    unittest.main()
