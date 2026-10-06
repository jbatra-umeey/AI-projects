"use strict";

const $ = (id) => document.getElementById(id);
const stages = [
  "User Goal",
  "Agent",
  "State/Memory",
  "Decision",
  "Tool",
  "Execution",
  "Observation",
  "Evaluation",
  "Next Action",
];
let snapshot = null;
let busy = false;

function element(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined) node.textContent = text;
  return node;
}

async function api(path, body) {
  const response = await fetch(
    path,
    body === undefined
      ? {}
      : {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(body),
        },
  );
  const result = await response.json();
  if (!response.ok) throw new Error(result.error || "Request failed");
  return result;
}

function controls() {
  const running = snapshot?.run.status === "running";
  for (const id of ["start", "refresh", "approve", "deny"])
    $(id).disabled = busy;
  $("step").disabled = busy || !running;
  $("play").disabled = busy || !running;
  $("export").disabled = !snapshot;
  $("history")
    .querySelectorAll("button")
    .forEach((b) => {
      b.disabled = busy;
    });
}

async function work(fn) {
  if (busy) return;
  busy = true;
  $("error").hidden = true;
  controls();
  try {
    await fn();
  } catch (error) {
    $("error").textContent = error.message;
    $("error").hidden = false;
  } finally {
    busy = false;
    controls();
  }
}

function eventDescription(event) {
  const p = event.payload;
  if (p.rationale) return p.rationale;
  if (p.goal) return p.goal;
  if (p.summary) return p.summary;
  if (p.approval !== undefined)
    return p.approval
      ? "Human approved the local simulation."
      : "Human denied the simulation. Run stopped.";
  if (p.data)
    return `${p.tool} returned ${p.data.id}. Open the payload to inspect its source and values.`;
  if (p.error) return p.error;
  if (p.action)
    return `${p.action.replaceAll("_", " ")}${p.reason ? " · " + p.reason.replaceAll("_", " ") : ""}`;
  if (p.gate)
    return `${p.passed ? "Passed" : "Failed"} · ${p.gate.replaceAll("_", " ")}${p.reason ? " · " + p.reason : ""}`;
  if (p.checks)
    return `${Object.values(p.checks).filter(Boolean).length}/${Object.keys(p.checks).length} evidence checks passed.`;
  if (p.planner)
    return `${p.orchestrator} orchestration · ${p.planner} planner`;
  if (p.tool) return `${p.tool} · attempt ${p.attempt}`;
  if (p.name)
    return `${p.name} · ${p.risk === "approval" ? "human approval required" : "read-only capability"}`;
  if (p.evidence_keys)
    return `${p.evidence_keys.length} evidence records · ${p.budget_remaining} decisions remaining`;
  if (p.historical_hints)
    return `${p.historical_hints.length} prior investigation hints loaded for revalidation.`;
  return "State transition recorded.";
}

function render(data) {
  snapshot = data;
  const { run, events } = data;
  localStorage.setItem("agentloop-run", run.id);
  $("status").textContent = run.status.replaceAll("_", " ");
  $("engine-state").textContent = run.status.replaceAll("_", " ").toUpperCase();
  $("run-id").textContent = "Run " + run.id.slice(0, 8);
  $("steps").replaceChildren(
    document.createTextNode(`${run.steps} `),
    element("i", "", `/ ${run.max_steps}`),
  );
  $("score").textContent = run.result
    ? `${Math.round(run.result.evaluation.score * 100)}%`
    : "—";
  $("tokens").textContent = run.tokens.toLocaleString();
  $("mode-label").textContent =
    run.planner === "demo" ? "Demo policy · no LLM" : "Reported by Ollama";
  $("checkpoint").textContent = `Decision ${run.steps} saved`;
  $("evidence-count").textContent =
    `${Object.keys(run.evidence).length} sources`;
  $("hint-count").textContent = run.memories.length;
  $("memory-count").textContent = Object.keys(run.evidence).length;
  $("state-json").textContent = JSON.stringify(run, null, 2);
  $("approval").hidden = run.status !== "awaiting_approval";
  $("proposal-json").textContent = JSON.stringify(
    run.evidence.proposal || {},
    null,
    2,
  );

  const seen = new Set(events.map((e) => e.stage));
  document.querySelectorAll(".stage").forEach((node, i) => {
    node.classList.toggle("visited", seen.has(stages[i]));
    node.classList.toggle("active", stages[i] === events.at(-1)?.stage);
  });
  const trace = $("trace");
  const wasAtBottom =
    trace.scrollHeight - trace.scrollTop - trace.clientHeight < 90;
  trace.replaceChildren(
    ...events.map((event, i) => {
      const row = element(
        "article",
        "event" +
          (event.stage === "Evaluation" ? " evaluation-event" : "") +
          (event.payload.action === "request_approval"
            ? " approval-event"
            : ""),
      );
      const content = element("div");
      const heading = element("div", "event-title");
      heading.append(
        element("h3", "", event.stage),
        element("span", "event-stage", `STEP ${stepFor(events, i)}`),
      );
      const details = element("details");
      details.append(
        element("summary", "", "Inspect payload"),
        element("pre", "", JSON.stringify(event.payload, null, 2)),
      );
      content.append(
        heading,
        element("p", "", eventDescription(event)),
        details,
      );
      const time = element(
        "time",
        "",
        new Date(event.timestamp).toLocaleTimeString([], { hour12: false }),
      );
      time.dateTime = event.timestamp;
      row.append(
        element("span", "event-index", String(i + 1).padStart(2, "0")),
        content,
        time,
      );
      return row;
    }),
  );
  if (wasAtBottom) trace.scrollTop = trace.scrollHeight;
  $("result").hidden = !run.result;
  if (run.result) {
    $("result-summary").textContent = run.result.summary;
    $("checks").replaceChildren(
      ...Object.entries(run.result.evaluation.checks).map(([key, value]) =>
        element(
          "div",
          "check" + (value ? "" : " fail"),
          `${value ? "✓" : "!"} ${key.replaceAll("_", " ")}`,
        ),
      ),
    );
    $("citations").textContent =
      `Evidence: ${run.result.evidence_ids.join(" · ")}. Synthetic fixtures; causality is not established.`;
  }
  controls();
}

function stepFor(events, index) {
  for (let i = index; i >= 0; i--)
    if (events[i].payload.step) return events[i].payload.step;
  return 0;
}

async function history() {
  const runs = await api("/api/runs");
  $("history").replaceChildren(
    ...runs.slice(0, 6).map((run) => {
      const button = element(
        "button",
        "history-item",
        run.scenario.replaceAll("_", " "),
      );
      button.append(
        element(
          "small",
          "",
          `${run.id.slice(0, 8)} · ${run.status.replaceAll("_", " ")} · ${run.steps} steps`,
        ),
      );
      button.addEventListener("click", () =>
        work(async () => render(await api(`/api/runs/${run.id}`))),
      );
      return button;
    }),
  );
  if (!runs.length)
    $("history").append(
      element("p", "hint", "Your saved runs will appear here."),
    );
}

$("stages").replaceChildren(
  ...stages.map((name, i) => {
    const node = element("div", "stage");
    node.append(
      element("span", "number", String(i + 1).padStart(2, "0")),
      element("span", "name", name),
    );
    return node;
  }),
);
$("launch-form").addEventListener("submit", (event) => {
  event.preventDefault();
  work(async () => {
    render(
      await api("/api/runs", {
        goal: $("goal").value,
        scenario: $("scenario").value,
        planner: $("planner").value,
        max_steps: Number($("budget").value),
      }),
    );
    await history();
  });
});
$("step").addEventListener("click", () =>
  work(async () => {
    render(await api(`/api/runs/${snapshot.run.id}/step`, {}));
    await history();
  }),
);
$("play").addEventListener("click", () =>
  work(async () => {
    while (snapshot.run.status === "running") {
      render(await api(`/api/runs/${snapshot.run.id}/step`, {}));
      await new Promise((resolve) => setTimeout(resolve, 180));
    }
    await history();
  }),
);
for (const [id, approved] of [
  ["approve", true],
  ["deny", false],
]) {
  $(id).addEventListener("click", () =>
    work(async () => {
      render(await api(`/api/runs/${snapshot.run.id}/approval`, { approved }));
      await history();
    }),
  );
}
$("refresh").addEventListener("click", () => work(history));
$("export").addEventListener("click", () => {
  const url = URL.createObjectURL(
    new Blob([JSON.stringify(snapshot, null, 2)], { type: "application/json" }),
  );
  const link = element("a");
  link.href = url;
  link.download = `agentloop-${snapshot.run.id}.json`;
  link.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
});
work(async () => {
  const config = await api("/api/config");
  for (const [value, title] of Object.entries(config.scenarios)) {
    const option = element("option", "", title);
    option.value = value;
    $("scenario").append(option);
  }
  await history();
  const previous = localStorage.getItem("agentloop-run");
  if (previous) {
    try {
      render(await api(`/api/runs/${previous}`));
    } catch {
      localStorage.removeItem("agentloop-run");
    }
  }
});
