# Database Schema

The assignment uses **two SQLite databases** as required.

## 1. Domain database: `lab.db`
- `student`: roll number, department, training completion.
- `equipment`: name/category, training requirement, total/available units, optimistic version.
- `policy`: data-driven rules (`max_active_bookings`).
- `booking`: student + equipment + slot, unique to prevent duplicate booking.
- `notification`: outbound confirmation records with a unique dedupe key.
- `idempotency`: durable key + stored side-effect result.

Source schema: `schema/lab.sql`.

## 2. Agent database: `agent.db`
Created from `schema/agent.sql`. Stores durable conversation threads, queued/running runs, leases, attempts and recorded model/tool steps used for crash recovery.

SQLite is intentionally used for runtime because the weekend brief explicitly requires two SQLite databases. No generated `.db` file is committed/submitted; both databases are created and seeded automatically.
