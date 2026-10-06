"""Optional LangSmith export. The local SQLite trace is always available."""
import os


def tracing_settings() -> dict:
    enabled = os.environ.get("LANGSMITH_TRACING", "false").strip().lower() == "true"
    if enabled and not os.environ.get("LANGSMITH_API_KEY", "").strip():
        raise ValueError("LANGSMITH_TRACING=true requires LANGSMITH_API_KEY in the server environment")
    return {"enabled": enabled, "project_name": os.environ.get("LANGSMITH_PROJECT", "agentloop-studio")}


def graph_config(run, approval=None) -> dict:
    return {"recursion_limit": 200,
            "run_name": "agentloop.approval" if approval is not None else "agentloop.investigation",
            "tags": ["agentloop-studio", f"planner:{run.planner}", f"scenario:{run.scenario}"],
            "metadata": {"investigation_id": run.id, "scenario": run.scenario,
                         "planner": run.planner, "max_decisions": run.max_steps,
                         "synthetic_tools": True}}
