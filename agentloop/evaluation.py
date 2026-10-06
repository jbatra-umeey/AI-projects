"""Deterministic evidence gates, separate from model decision-making."""
from .domain import Run


def evaluate(run: Run) -> dict:
    metrics = run.evidence.get("metrics", {})
    deploy = run.evidence.get("deployments", {})
    checks = {
        "baseline_present": metrics.get("baseline_p95_ms", 0) > 0,
        "sufficient_samples": metrics.get("sample_size", 0) >= 100,
        "deployment_evidence_complete": deploy.get("complete") is True,
        "runbook_retrieved": "runbook" in run.evidence,
        "sources_traceable": all(v.get("id") and v.get("source") for v in run.evidence.values()),
    }
    remediation_required = bool(metrics) and metrics.get("current_p95_ms", 0) > metrics.get("baseline_p95_ms", 0) * 1.2
    checks["remediation_evidence_complete"] = not remediation_required or ("proposal" in run.evidence and "remediation" in run.evidence)
    score = round(sum(checks.values()) / len(checks), 3)
    return {"passed": all(checks.values()), "score": score, "checks": checks,
            "kind": "deterministic_evidence_gate", "causality": "not_established"}


def report(run: Run) -> dict:
    evaluation = evaluate(run)
    metrics = run.evidence.get("metrics", {})
    base = metrics.get("baseline_p95_ms", 0)
    change = round((metrics.get("current_p95_ms", 0) / base - 1) * 100, 1) if base else None
    if not evaluation["passed"]:
        summary = "Insufficient verified evidence to complete the investigation. Escalate for missing evidence."
    elif change is not None and change <= 20:
        summary = f"Latency changed {change:+.1f}% versus baseline and is within the 20% tolerance. No remediation needed."
    else:
        summary = (f"p95 latency increased {change:+.1f}% versus baseline. A recent synchronous image decode "
                   "change is a candidate contributor, not a proven root cause. The approved canary was simulated locally.")
    return {"summary": summary, "latency_change_pct": change, "evaluation": evaluation,
            "evidence_ids": [v["id"] for v in run.evidence.values()],
            "limitations": ["Synthetic fixtures only", "Temporal correlation does not establish causality",
                            "No real infrastructure is modified"]}
