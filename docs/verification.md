# Verification record

The following checks were completed against this project on Python 3.12.

| Area | Result | Scope |
|---|---|---|
| Python unit and integration suite | 34 tests passed | Runtime, graph routing, persistence, concurrent approval, policy failures, API, planner contract, trace configuration |
| Offline trajectory benchmark | 5 of 5 scenarios passed | Deterministic planner with synthetic fixtures; results in `examples/benchmark.json` |
| Browser flows | Passed | Approval, denial, evidence gate, memory reuse, reload recovery, JSON download, text-safe rendering, mobile overflow |
| JavaScript parse check | Passed | `node --check web/app.js` |
| Python dependency consistency | Passed | `pip check` |
| LangGraph execution | Exercised | Both one-decision and continuous feedback-loop invocation |
| Ollama live model | Not exercised | Mocked HTTP contract and invalid-response tests only |
| LangSmith hosted export | Not exercised | Opt-in configuration and runtime context tests only; requires an operator-provided API key |
| GitHub Actions | Configured, not executed during local verification | Python 3.12/3.13 contract jobs and browser job |

Browser checks used Playwright 1.62.1 with packaged Chromium 153 because the standard browser download returned an invalid archive in the build environment. The application ran on its local HTTP server. Desktop and mobile screenshots were captured from that running application and visually inspected.

No live production telemetry or external remediation was tested. No model-quality, load, multi-tenant, or security-certification claim is made by these results.

Reproduce the core checks:

```bash
python -m pip install -r requirements-lock.txt
python -m unittest discover -s tests -v
python -m agentloop.benchmark
```

For browser checks, start `python -m agentloop` in a separate terminal, then run `npm ci`, `npx playwright install chromium`, and `npm run test:browser`.
