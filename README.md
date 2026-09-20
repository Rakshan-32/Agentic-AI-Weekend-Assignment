# Lab Equipment Booking Agent — Agentic AI Weekend Project

A durable multi-agent service for campus lab equipment discovery and booking. Students can search equipment, check training/policy eligibility, book scarce equipment for a slot, and receive confirmation messages.

## Problem statement
Lab equipment is limited and manual booking can cause clashes, duplicate reservations and policy violations. This service uses a supervisor plus least-privilege specialists to safely answer availability questions and execute bookings. Rules are enforced by tools/data rather than trusting the model.

## Architecture
See [`SYSTEM_ARCHITECTURE.md`](SYSTEM_ARCHITECTURE.md).

```text
Student -> Durable Queue -> Worker/Lease -> Supervisor
                                      |-> Inventory Specialist (READ ONLY)
                                      |     -> Lab DB
                                      `-> Booking Specialist (READ+WRITE)
                                            -> Lab DB -> Notification
Agent DB stores threads, runs, steps, leases and retry state.
```

## Requirements covered
- Two SQLite databases: `lab.db` for domain data and `agent.db` for durable execution/memory.
- Six effective tools/delegations; four specialist domain tools plus two inventory tools, with explicit usage/change descriptions.
- Business rules stored in `policy` and equipment/student data; `book_equipment` re-enforces them.
- Durable queue, worker lease and expired-run recovery.
- Idempotency keys for every side effect; booking and notifications are independently repeat-safe.
- Supervisor + two specialists; Inventory Specialist has no write tools.
- Scripted models run without API key; crash replay is deterministic.
- 23 automated tests, including crash-and-replay and a threaded race test for the final equipment unit (higher-grade option).

## Run
Python 3.11+ recommended.

```bash
python -m pip install -r requirements.txt
python -m scripts.demo
python -m scripts.demo --crash
pytest
```

Expected verification: normal demo succeeds, crash demo prints `PASS`, and `pytest` reports `23 passed`.

## Optional Gemini check
Set `GEMINI_API_KEY` and run `python -m scripts.demo --real`. The scripted demo is the required offline proof and does not need a key.

## Database design
See [`DB_SCHEMA.md`](DB_SCHEMA.md) and [`schema/lab.sql`](schema/lab.sql). Runtime `.db` files are intentionally excluded from submission.

## Design choices
The inventory specialist is deliberately read-only. The booking specialist is bound to the current student's roll number so the model cannot choose another identity. Booking uses an atomic stock decrement plus a uniqueness constraint. Side effects are also wrapped in durable idempotency keys so a worker crash between the write and step recording cannot duplicate an action.
