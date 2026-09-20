# Database Schema

The project preserves the **two SQLite database structures required by the weekend brief** and also supports the instructor-requested **Supabase cloud persistence**.

## Required SQLite structures
1. `lab.db` / `schema/lab.sql`: `student`, `equipment`, `policy`, `booking`, `notification`, `idempotency`.
2. `agent.db` / `schema/agent.sql`: `thread`, `message`, `run`, `run_step`, `tool_call` for durable queue, leases, memory and replay.

The clean-machine scripted demo uses these SQLite schemas with no account or API key.

## Supabase cloud database
`schema/supabase.sql` is the PostgreSQL/Supabase mirror of both structures. When a local `.env` contains `SUPABASE_DB_URL`, `app.config.open_stores()` selects `CloudLabDb` and `CloudRunStore`, so domain data, runs, leases, messages, tool calls and idempotency results are stored in Supabase.

Secrets are never committed. `.env` is ignored and `.env.example` contains placeholders only.
