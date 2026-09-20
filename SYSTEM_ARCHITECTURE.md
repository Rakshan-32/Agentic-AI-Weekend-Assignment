# System Architecture — Lab Equipment Booking Agent

```mermaid
flowchart TD
    U[Student Request] --> Q[Durable Queue]
    Q --> W[Worker: claim + lease + heartbeat]
    W --> S[Supervisor Agent]
    S --> I[Inventory Specialist - READ ONLY]
    S --> B[Booking Specialist - READ + WRITE]
    I --> T[Tool Layer]
    B --> T
    T --> D[(Domain Data)]
    W --> A[(Agent Memory + Queue Data)]
    D --> P[Policy + training + stock]
    B --> N[Notification]
    W -. expired lease .-> R[Crash Recovery / Replay]
    R --> W
    D --> C[(Supabase PostgreSQL in cloud mode)]
    A --> C
    D -. zero-config grading mode .-> L1[(lab.db SQLite)]
    A -. zero-config grading mode .-> L2[(agent.db SQLite)]
```

## Execution modes
- **Clean-machine/offline grading:** two SQLite databases, scripted models, no API key.
- **Instructor cloud mode:** `SUPABASE_DB_URL` selects Supabase PostgreSQL; both domain data and durable agent data are persisted in the cloud. The SQLite schema files remain the canonical assignment structures.

## Durable flow
A question is persisted before execution. A worker claims it with a lease. The Supervisor delegates discovery to a read-only Inventory Specialist and actions to a Booking Specialist. Policy is read from data and rechecked inside write tools. Every side effect receives a deterministic idempotency key. If a worker dies, another worker reclaims the expired run and safely replays it without duplicating the booking or notification.
