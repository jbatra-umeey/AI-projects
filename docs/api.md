# Local API

Start with `python -m agentloop --port 8080 --db data/agentloop.db`. The API binds to `127.0.0.1` and accepts loopback Host headers. It has no user authentication; use it locally.

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/config` | Scenario catalog |
| GET | `/api/runs` | 50 most recently saved runs |
| GET | `/api/runs/{id}` | Run snapshot and ordered event trace |
| POST | `/api/runs` | Create a run |
| POST | `/api/runs/{id}/step` | Execute one decision boundary |
| POST | `/api/runs/{id}/advance` | Follow the LangGraph loop until pause or termination |
| POST | `/api/runs/{id}/approval` | Approve or deny the saved simulation decision |

POST requests require `Content-Type: application/json` and a body of at most 16 KiB. Step and advance use `{}`. Unknown fields are rejected. GET run and all successful mutations return `{"run": {...}, "events": [...]}`. Creation returns HTTP 201, successful reads/actions return 200, malformed input returns 400, and unknown resources return 404. Content-type, body-size, and origin/host rejection return 415, 413, and 403 respectively.

## Create an investigation

```bash
curl http://127.0.0.1:8080/api/runs \
  -H 'Content-Type: application/json' \
  -d '{"goal":"Investigate Android editor latency","scenario":"regression","planner":"demo","max_steps":8}'
```

Use the returned `run.id` in subsequent requests:

```bash
curl http://127.0.0.1:8080/api/runs/RUN_ID/advance \
  -H 'Content-Type: application/json' -d '{}'

curl http://127.0.0.1:8080/api/runs/RUN_ID/approval \
  -H 'Content-Type: application/json' -d '{"approved":true}'

curl http://127.0.0.1:8080/api/runs/RUN_ID/advance \
  -H 'Content-Type: application/json' -d '{}'
```

An approval call executes the already-selected simulated tool and saves its observation. Use step or advance afterward to evaluate completion. A second approval is rejected. Calling step or advance on a terminal run is a no-op.

## Python interface

```python
from agentloop.runtime import Runtime
from agentloop.store import Store

runtime = Runtime(Store("data/example.db"))
run = runtime.start("Investigate latency", scenario="regression")
run = runtime.run_until_pause(run.id)
assert run.status == "awaiting_approval"

# An interactive application should obtain a human decision here.
runtime.approve(run.id, approved=True)
run = runtime.run_until_pause(run.id)
print(run.result["summary"])
```

Statuses are `running`, `awaiting_approval`, `completed`, `blocked`, `budget_exhausted`, `failed`, and `cancelled`.
