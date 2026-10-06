# Architecture and design decisions

## State and responsibility

The runtime is a bounded state machine implemented as a LangGraph `StateGraph`. The planner chooses a tool; application policy decides whether it may run. A separate evaluator determines whether the collected evidence is sufficient to finish.

| Lifecycle stage | Implementation | Observable output |
|---|---|---|
| User Goal | `Runtime.start()` validates the goal, scenario, and step budget | Goal event |
| Agent | Demo or Ollama planner configured for the run | Planner and orchestrator event |
| State/Memory | `restore_memory` reads the current run; start retrieves recent successful runs | Evidence keys, historical hints, remaining budget |
| Decision | `decide` produces a validated `Decision` | Tool name, empty arguments, brief rationale |
| Tool | `select_tool` enforces capabilities and prerequisites | Allowed tool and risk level, or policy rejection |
| Execution | `execute_tool` invokes one registered function | Attempt count and tool name |
| Observation | `observe` records the result as source-labeled evidence | Tool payload or failure |
| Evaluation | `evaluate` records per-tool outcome or the final evidence gate | Check results and limitations |
| Next Action | `next_action` commits the boundary and routes to continue or stop | Continue, retry, approval, finish, escalation, or budget stop |

`LoopState` is a typed LangGraph state contract. Its `Run` contains the goal, scenario, planner, budget, attempts, evidence, memories, pending decision, result, and reported token usage. Per-invocation fields hold the decision, observation, error, approval input, and event batch. Current node functions mutate the in-memory `Run`; the durable boundary is the explicit checkpoint transaction.

## Why LangGraph

The workload has feedback and branching: retry a tool, continue gathering evidence, stop on policy failure, wait for human input, or finish. Named nodes and conditional edges make those transitions inspectable. `Runtime.run_until_pause()` traverses the feedback edge within one graph invocation. `Runtime.step()` ends after one decision boundary so the UI can show progress and let the operator inspect payloads.

LangGraph does not determine whether an operation is authorized. The tool policy and evaluator remain ordinary testable Python code. This makes it possible to replace the planner without weakening execution constraints.

## Persistence and recovery

SQLite is the authoritative application store, with three tables:

| Table | Data |
|---|---|
| `runs` | Latest serializable `Run` snapshot |
| `events` | Ordered lifecycle event journal |
| `memories` | Successful, evaluated investigation summaries keyed by scenario and originating run |

Each decision boundary saves the run snapshot and its event batch in one SQLite transaction. A completed investigation's memory write is part of the same transaction. WAL mode allows local readers while data is being written. Queries use bound parameters.

This is **application-level checkpointing**, not a LangGraph native checkpointer. A pending approval is stored on the run and the graph ends. On approval, the runtime reloads that decision and enters the execution path. On restart, a running investigation resumes from the latest saved decision boundary. A process crash inside a tool can cause that tool to replay; this design does not promise exactly-once execution.

This choice keeps the demo's business state and audit batch atomic in one store. Native LangGraph `interrupt()` plus `SqliteSaver` or `PostgresSaver` would add checkpoint history at graph super-step granularity, replay, and richer long-running workflow facilities. A production migration must choose an authoritative state owner and reconcile business events with checkpoint commits rather than blindly dual-writing them.

## Memory semantics

Working memory is the evidence gathered in the current investigation. Historical memory contains up to three recent successful investigation summaries for the same scenario. Each hint carries a `source_run` and `trust: historical_hint`.

Hints never populate current evidence or satisfy an evidence gate. The demo planner always gathers fresh evidence; the Ollama planner receives the hints as explicitly untrusted context and remains subject to the same prerequisites. Retrieval here is a scenario-key lookup, not vector search or RAG. A real system would need tenant boundaries, timestamps, expiration, source access checks, and relevance ranking.

## Authorization and failure boundaries

- Only names present in `TOOLS` can execute. All current tools take empty arguments.
- Remediation requires metrics, complete deployment evidence, retrieved guidance, a measured regression, and a proposal.
- The simulation requires an explicit boolean approval. Repeated or concurrent approval within one runtime cannot execute the simulation twice.
- A reentrant process lock serializes graph execution and snapshot reads. This is a single-process guarantee, not a distributed lock.
- Unknown tools, repeated successful tools, malformed decisions, and invalid arguments stop the run.
- A transient failure receives at most one retry. The retry consumes another decision step. Other tool/planner failures stop the run.
- The budget counts planner decisions, including `finish`, not LangGraph nodes. Approval executes an already-budgeted decision. Maximum is 20 decisions; graph recursion is capped separately at 200 node transitions.
- The Ollama call has a 30-second HTTP timeout. The demo tools do no network I/O. There is no universal wall-clock deadline or currency budget.

The API is a loopback-only development server. It restricts Host headers, cross-origin writes, request content type and size, and static file paths. The UI renders untrusted text with DOM `textContent`. These controls do not substitute for authentication if the app is exposed outside a local machine.

## Evaluation and observability

The final evaluator checks baseline availability, sample count, complete deployment evidence, runbook presence, source identifiers, and remediation evidence when required. It reports a fraction of passed checks. This score is **not a probability of a correct diagnosis**. A report describes a candidate contributor and explicitly states that causality is not established.

The event journal captures each of the user's nine lifecycle stages. It stores concise decision summaries, not model private reasoning. Ollama token totals come from provider-reported counts; demo mode records zero. The current app does not estimate monetary cost or instrument OpenTelemetry. Run JSON export supports inspecting and comparing trajectories outside the UI.

Optional LangSmith tracing wraps each graph invocation in an explicit tracing context. Export defaults to disabled. An enabled configuration requires an API key in the environment. Graph invocations have planner/scenario tags and a shared `investigation_id` in metadata so separate step and approval traces can be correlated. The graph automatically emits node traces through its LangChain integration. The custom Ollama HTTP call is represented inside the decision node; no separate LangSmith LLM token/cost span is claimed. Hosted datasets, online evaluators, and prompt experiments are future extensions.

## Extending the system

1. Add a read-only tool adapter with validated inputs and source metadata. Keep credentials in the operator's environment; do not place secrets in observations or the database.
2. Define policy prerequisites and update the planner's advertised tool schema.
3. Add representative fixtures and an adversarial planner test before adding any action capability.
4. Add a real model evaluation dataset separately from deterministic trajectory tests. Record model/version, prompt version, latency, token usage, expected behavior, and human review criteria.
5. Before external writes, implement idempotency keys, approval identity and expiry, action-specific scope, and crash reconciliation.

Potential production architecture: authenticated API, per-tenant durable graph threads, a worker queue, PostgreSQL checkpointer/business store with a defined consistency model, a versioned tool gateway, and traces/metrics. These are design directions, not shipped components.

## Primary references

- [LangGraph Graph API](https://docs.langchain.com/oss/python/langgraph/graph-api)
- [LangGraph interrupts](https://docs.langchain.com/oss/python/langgraph/interrupts) — an alternative checkpoint/approval design
- [Ollama generate API](https://docs.ollama.com/api/generate)
