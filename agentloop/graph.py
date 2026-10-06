"""The actual LangGraph StateGraph: nodes, policy branches, and feedback edge.

SQLite checkpoints at decision boundaries are owned by the application. This
keeps each run snapshot, event batch and successful memory write atomic. It is
not a LangGraph checkpointer; see docs/architecture.md for the trade-off.
"""
from dataclasses import asdict
from typing import TypedDict

from langgraph.graph import END, START, StateGraph

from .domain import Decision, Run, TERMINAL
from .evaluation import report
from .planners import DemoPlanner, OllamaPlanner
from .tools import TOOLS, TransientError

KEYS = {"query_metrics": "metrics", "list_deployments": "deployments", "retrieve_runbook": "runbook",
        "propose_remediation": "proposal", "simulate_remediation": "remediation"}


class LoopState(TypedDict, total=False):
    run: Run
    events: list[tuple[str, dict]]
    decision: Decision | None
    observation: dict | None
    error: str | None
    retryable: bool
    continuous: bool
    approval: bool | None
    route: str


def build_graph(store, planner_override=None):
    def restore_memory(state: LoopState):
        run = state["run"]
        events = []
        approval = state.get("approval")
        if approval is not None:
            if run.status != "awaiting_approval" or run.pending is None:
                raise ValueError("Run has no pending approval")
            decision = Decision.parse(run.pending)
            if decision.tool != "simulate_remediation" or decision.arguments:
                raise ValueError("Invalid pending approval")
            run.pending = None
            events.append(("Decision", {"approval": approval, "tool": decision.tool, "actor": "local_user"}))
            run.status = "running" if approval else "cancelled"
            if not approval:
                events.append(("Next Action", {"action": "stop", "reason": "approval_denied"}))
            return {"decision": decision, "events": events, "approval": None,
                    "route": "execute_tool" if approval else "next_action"}
        if run.status in TERMINAL or run.status == "awaiting_approval":
            return {"events": [], "route": "next_action"}
        if run.steps >= run.max_steps:
            run.status = "budget_exhausted"
            return {"events": [("Next Action", {"action": "stop", "reason": "step_budget_exhausted"})],
                    "route": "next_action"}
        run.steps += 1
        events.append(("State/Memory", {"step": run.steps, "evidence_keys": list(run.evidence),
                                        "budget_remaining": run.max_steps - run.steps}))
        return {"events": events, "decision": None, "observation": None, "error": None,
                "retryable": False, "route": "decide"}

    def decide(state: LoopState):
        run, events = state["run"], list(state["events"])
        try:
            planner = planner_override or (DemoPlanner() if run.planner == "demo" else OllamaPlanner())
            decision = Decision.parse(asdict(planner.decide(run)))
            events.append(("Decision", asdict(decision)))
            return {"decision": decision, "events": events, "route": "select_tool"}
        except (ValueError, TypeError, KeyError) as exc:
            run.status = "blocked"
            return {"events": events + [("Evaluation", {"passed": False, "reason": str(exc), "gate": "decision_schema"}),
                                        ("Next Action", {"action": "stop", "reason": "invalid_decision"})],
                    "route": "next_action"}
        except Exception as exc:
            run.status = "failed"
            return {"events": events + [("Observation", {"error_type": type(exc).__name__, "message": "Planner failed"}),
                                        ("Next Action", {"action": "stop", "reason": "planner_failure"})],
                    "route": "next_action"}

    def select_tool(state: LoopState):
        run, decision, events = state["run"], state["decision"], list(state["events"])
        try:
            if decision.arguments:
                raise ValueError("These tools accept no arguments")
            if decision.tool == "finish":
                return {"route": "evaluate"}
            if decision.tool not in TOOLS:
                raise ValueError(f"Tool is not allowlisted: {decision.tool}")
            if KEYS[decision.tool] in run.evidence:
                raise ValueError("Successful tools cannot be repeated")
            if decision.tool in {"propose_remediation", "simulate_remediation"}:
                if not {"metrics", "deployments", "runbook"} <= run.evidence.keys():
                    raise ValueError("Collect metrics, deployments and runbook before remediation")
                m = run.evidence["metrics"]
                if m["current_p95_ms"] <= m["baseline_p95_ms"] * 1.2 or not run.evidence["deployments"]["complete"]:
                    raise ValueError("Remediation requires regression and complete deployment evidence")
            if decision.tool == "simulate_remediation" and "proposal" not in run.evidence:
                raise ValueError("A remediation proposal must precede approval")
            tool = TOOLS[decision.tool]
            events.append(("Tool", {"name": tool.name, "risk": tool.risk, "allowlisted": True}))
            if tool.risk == "approval":
                run.pending, run.status = asdict(decision), "awaiting_approval"
                events.append(("Next Action", {"action": "request_approval", "proposal": run.evidence["proposal"]}))
                return {"events": events, "route": "next_action"}
            return {"events": events, "route": "execute_tool"}
        except ValueError as exc:
            run.status = "blocked"
            return {"events": events + [("Evaluation", {"passed": False, "reason": str(exc), "gate": "policy"}),
                                        ("Next Action", {"action": "stop", "reason": "policy_rejected_decision"})],
                    "route": "next_action"}

    def execute_tool(state: LoopState):
        run, decision, events = state["run"], state["decision"], list(state["events"])
        tool = TOOLS[decision.tool]
        run.attempts[tool.name] = run.attempts.get(tool.name, 0) + 1
        events.append(("Execution", {"tool": tool.name, "attempt": run.attempts[tool.name]}))
        try:
            return {"events": events, "observation": tool.execute(run), "error": None, "retryable": False}
        except TransientError as exc:
            retryable = run.attempts[tool.name] < 2
            if not retryable:
                run.status = "failed"
            return {"events": events, "observation": None, "error": str(exc), "retryable": retryable}
        except Exception as exc:
            run.status = "failed"
            return {"events": events, "observation": None, "error": f"Tool failed: {type(exc).__name__}", "retryable": False}

    def observe(state: LoopState):
        events, tool = list(state["events"]), state["decision"].tool
        if state["error"]:
            events.append(("Observation", {"tool": tool, "error": state["error"], "retryable": state["retryable"]}))
        else:
            state["run"].evidence[KEYS[tool]] = state["observation"]
            events.append(("Observation", {"tool": tool, "data": state["observation"], "trust": "tool_data"}))
        return {"events": events}

    def evaluate(state: LoopState):
        run, events = state["run"], list(state["events"])
        if state["decision"].tool == "finish":
            run.result = report(run)
            run.status = "completed" if run.result["evaluation"]["passed"] else "blocked"
            events.extend([("Evaluation", run.result["evaluation"]),
                           ("Next Action", {"action": "finish" if run.status == "completed" else "escalate",
                                            "summary": run.result["summary"]})])
        elif state["error"]:
            events.extend([("Evaluation", {"passed": False, "reason": "tool_failure"}),
                           ("Next Action", {"action": "retry" if state["retryable"] else "stop"})])
        else:
            events.extend([("Evaluation", {"passed": True, "gate": "observation_recorded", "evidence_id": state["observation"]["id"]}),
                           ("Next Action", {"action": "continue"})])
        return {"events": events}

    def next_action(state: LoopState):
        if state["events"]:
            store.checkpoint(state["run"], state["events"])
        return {"events": [], "route": "restore_memory" if state["continuous"] and state["run"].status == "running" else END}

    builder = StateGraph(LoopState)
    for name, node in [("restore_memory", restore_memory), ("decide", decide), ("select_tool", select_tool),
                       ("execute_tool", execute_tool), ("observe", observe), ("evaluate", evaluate),
                       ("next_action", next_action)]:
        builder.add_node(name, node)
    builder.add_edge(START, "restore_memory")
    builder.add_conditional_edges("restore_memory", lambda s: s["route"], ["decide", "execute_tool", "next_action"])
    builder.add_conditional_edges("decide", lambda s: s["route"], ["select_tool", "next_action"])
    builder.add_conditional_edges("select_tool", lambda s: s["route"], ["execute_tool", "evaluate", "next_action"])
    builder.add_edge("execute_tool", "observe")
    builder.add_edge("observe", "evaluate")
    builder.add_edge("evaluate", "next_action")
    builder.add_conditional_edges("next_action", lambda s: s["route"], ["restore_memory", END])
    return builder.compile(name="AgentLoopStudio")
