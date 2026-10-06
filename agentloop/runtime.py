"""Application facade around LangGraph with atomic SQLite decision checkpoints."""
from threading import RLock

from langsmith import tracing_context

from .domain import Run
from .graph import build_graph
from .observability import graph_config, tracing_settings
from .planners import OllamaPlanner
from .store import Store
from .tools import SCENARIOS


class Runtime:
    def __init__(self, store: Store, planner=None):
        self.store = store
        self.lock = RLock()
        self.graph = build_graph(store, planner)

    def start(self, goal: str, scenario="regression", planner="demo", max_steps=8) -> Run:
        if not isinstance(goal, str) or not goal.strip() or len(goal) > 2000:
            raise ValueError("Goal must contain 1–2000 characters")
        if not isinstance(scenario, str) or scenario not in SCENARIOS:
            raise ValueError("Unknown scenario")
        if not isinstance(planner, str) or planner not in {"demo", "ollama"}:
            raise ValueError("Unknown planner")
        if type(max_steps) is not int or not 1 <= max_steps <= 20:
            raise ValueError("Step budget must be an integer from 1 to 20")
        if planner == "ollama":
            OllamaPlanner()
        tracing_settings()
        with self.lock:
            run = Run(goal.strip(), scenario, planner, max_steps)
            run.memories = self.store.memories(scenario)
            self.store.checkpoint(run, [
                ("User Goal", {"goal": run.goal, "scenario": scenario}),
                ("Agent", {"planner": planner, "orchestrator": "LangGraph", "policy": "bounded incident investigation"}),
                ("State/Memory", {"historical_hints": run.memories, "trust": "revalidate_with_current_tools"}),
            ])
            return run

    def _invoke(self, run_id, continuous=False, approval=None):
        with self.lock:
            run = self.store.get(run_id)
            with tracing_context(**tracing_settings()):
                result = self.graph.invoke({"run": run, "events": [], "continuous": continuous,
                                            "approval": approval}, graph_config(run, approval))
            return result["run"]

    def step(self, run_id: str) -> Run:
        return self._invoke(run_id)

    def run_until_pause(self, run_id: str) -> Run:
        """Follow the graph's feedback edge until approval, completion or budget exhaustion."""
        return self._invoke(run_id, continuous=True)

    def approve(self, run_id: str, approved: bool) -> Run:
        if type(approved) is not bool:
            raise ValueError("approved must be a boolean")
        return self._invoke(run_id, approval=approved)

    def snapshot(self, run_id: str) -> dict:
        with self.lock:
            return {"run": self.store.get(run_id).to_dict(), "events": self.store.events(run_id)}
