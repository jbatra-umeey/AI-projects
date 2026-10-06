# Security and data scope

AgentLoop Studio is a single-user local reference application. The bundled tools read synthetic fixtures or record a local simulation. They do not call production systems, run shell commands, read credentials, or execute deployment changes.

The application enforces tool-name and argument validation, prerequisites, approval before simulation, decision budgets, loopback Host validation, same-origin writes, and text-only rendering of tool data. These are specific tested controls, not a security certification or a guarantee against all prompt injection.

The SQLite database contains goals, tool results, and run history without application-level encryption. Do not enter sensitive production data in this reference demo. A configured Ollama endpoint receives the goal, collected evidence, and historical hints. `OLLAMA_URL` is operator configuration, not a browser-supplied value. Enabling LangSmith tracing exports graph inputs and outputs to the configured service; it is off by default. API keys remain environment configuration and are not included in run state.

Do not expose the development HTTP server publicly. It lacks authentication, tenant isolation, role-based approval, distributed locking, retention policies, and production rate limiting. The process lock only coordinates one runtime instance. Crash recovery can replay a tool that ran before the last checkpoint commit.

For a suspected issue, use a private reporting channel offered by the repository owner if one is available. Avoid posting secrets or exploit payloads containing real data in public issues.
