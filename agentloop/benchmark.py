"""Reproducible offline trajectory benchmark, not a model-quality benchmark."""
import argparse
import json
import tempfile
from pathlib import Path

from .domain import TERMINAL
from .runtime import Runtime
from .store import Store
from .tools import SCENARIOS


def benchmark() -> dict:
    results = []
    with tempfile.TemporaryDirectory() as temp:
        runtime = Runtime(Store(str(Path(temp) / "bench.db")))
        for scenario in SCENARIOS:
            run = runtime.start("Investigate Android editor latency", scenario)
            while run.status not in TERMINAL:
                run = runtime.approve(run.id, True) if run.status == "awaiting_approval" else runtime.run_until_pause(run.id)
            events = runtime.store.events(run.id)
            calls = [e["payload"]["tool"] for e in events if e["stage"] == "Execution"]
            expected = "blocked" if scenario == "insufficient" else "completed"
            approved = False
            approval_respected = True
            for event in events:
                if event["stage"] == "Decision" and event["payload"].get("approval") is True:
                    approved = True
                if event["stage"] == "Execution" and event["payload"]["tool"] == "simulate_remediation":
                    approval_respected = approval_respected and approved
                    approved = False
            checks = {"expected_status": run.status == expected,
                      "bounded": run.steps <= run.max_steps,
                      "approval_respected": approval_respected,
                      "only_allowlisted_tools": not any(c not in {"query_metrics", "list_deployments", "retrieve_runbook", "propose_remediation", "simulate_remediation"} for c in calls),
                      "evaluation_matches_expectation": bool(run.result and run.result["evaluation"]["passed"]) == (expected == "completed")}
            if scenario == "transient":
                checks["retried_once"] = calls.count("query_metrics") == 2
            if scenario == "healthy":
                checks["no_remediation"] = "simulate_remediation" not in calls
            results.append({"scenario": scenario, "status": run.status, "steps": run.steps,
                            "tool_executions": len(calls), "checks": checks, "passed": all(checks.values())})
    return {"benchmark": "offline trajectory contracts", "planner": "deterministic demo",
            "scenarios": len(results), "passed": sum(r["passed"] for r in results), "results": results}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output")
    args = parser.parse_args()
    result = benchmark()
    encoded = json.dumps(result, indent=2)
    if args.output:
        Path(args.output).write_text(encoded + "\n")
    print(encoded)
    raise SystemExit(0 if result["passed"] == result["scenarios"] else 1)


if __name__ == "__main__":
    main()
