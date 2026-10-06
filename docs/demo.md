# Five-minute engineering demo

## 1. Show the complete lifecycle

Start the server, open the dashboard, select the regression scenario, and launch an investigation. Explain the difference between an agent's proposed decision and the runtime's authority to execute it. Click **Step once** and inspect the metric observation: baseline p95 is 800 ms and current p95 is 1,920 ms in this synthetic fixture.

Click **Run to checkpoint**. Show the deployment and runbook evidence, then the canary proposal. The agent pauses for approval. Refresh the page or restart the server with the same database: the pending decision remains available.

## 2. Demonstrate controlled execution

Approve the simulation, then run to completion. The report calculates a 140% latency increase and identifies synchronous image decoding as a candidate contributor. It does not claim that temporal correlation proves the root cause. Expand the six evidence checks and export the run JSON.

Start a second investigation. The previous successful run appears as a historical hint, while the new run starts with no current evidence. Fresh tool calls still run.

## 3. Show failure behavior

Choose **Telemetry timeout, then recovery**. Inspect the failed observation, retry action, and second metrics attempt. Then choose **Missing deployment evidence**: the agent escalates and does not request remediation approval. With a step budget of 2, demonstrate a bounded stop.

Choose the injected-runbook scenario. Open the retrieved text and point to the malicious instructions. Explain that the deterministic planner doesn't follow document instructions, while separate adversarial planner tests prove that a request for `shell_exec` is rejected by the execution policy.

## 4. Explain the code and trade-offs

Open `agentloop/graph.py` and show the LangGraph nodes and `next_action → restore_memory` edge. Open the SQLite transaction in `store.py`. Discuss why checkpoints are owned by the application in this version, and how native LangGraph checkpointing would change recovery granularity.

Open `tests/test_runtime.py`: restart recovery, duplicate approval, concurrent approval, forbidden tools, premature completion, and budget enforcement are executable contracts. Run:

```bash
python -m unittest discover -s tests -v
python -m agentloop.benchmark
```

## 5. Be precise about the scope

Explain which components are real (LangGraph, SQLite, UI, policy, evaluator, local-model adapter) and which data/actions are synthetic. Demo mode is a deterministic baseline. Ollama mode makes model-driven decisions but still uses the same fixture tools; its live quality has not been benchmarked.

Useful discussion questions:

- Where does authorization live when the model suggests a tool?
- What is persisted before and after approval?
- What happens if the process dies during execution?
- How do historical hints avoid becoming stale evidence?
- How would the system isolate tenants and authenticate approvers?
- Which metrics describe orchestration correctness versus model quality?
- What must change before replacing a local simulation with a real rollback?
