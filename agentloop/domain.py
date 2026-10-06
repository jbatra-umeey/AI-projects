"""Serializable contracts shared by planners, tools, storage and the UI."""
from dataclasses import asdict, dataclass, field
from typing import Any
from uuid import uuid4

STAGES = ["User Goal", "Agent", "State/Memory", "Decision", "Tool", "Execution", "Observation", "Evaluation", "Next Action"]
TERMINAL = {"completed", "blocked", "budget_exhausted", "failed", "cancelled"}


@dataclass
class Decision:
    tool: str
    rationale: str
    arguments: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def parse(cls, data: Any) -> "Decision":
        if not isinstance(data, dict) or set(data) != {"tool", "rationale", "arguments"}:
            raise ValueError("Decision must contain exactly tool, rationale and arguments")
        if not isinstance(data["tool"], str) or not isinstance(data["rationale"], str):
            raise ValueError("Tool and rationale must be strings")
        if not data["rationale"].strip() or len(data["rationale"]) > 1000:
            raise ValueError("Rationale must contain 1–1000 characters")
        if not isinstance(data["arguments"], dict):
            raise ValueError("Arguments must be an object")
        return cls(**data)


@dataclass
class Run:
    goal: str
    scenario: str = "regression"
    planner: str = "demo"
    max_steps: int = 8
    id: str = field(default_factory=lambda: uuid4().hex)
    status: str = "running"
    steps: int = 0
    evidence: dict[str, Any] = field(default_factory=dict)
    memories: list[dict[str, Any]] = field(default_factory=list)
    attempts: dict[str, int] = field(default_factory=dict)
    pending: dict[str, Any] | None = None
    result: dict[str, Any] | None = None
    tokens: int = 0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
