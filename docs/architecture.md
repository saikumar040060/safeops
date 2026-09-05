# SafeOps Architecture

SafeOps is a security and control plane for autonomous AI agents. It sits
between an agent and the real tools it wants to call, enforcing permissions,
policy, and risk assessment before anything executes.

## Flow

```
User Task
  -> Agent Runtime
  -> Tool Gateway
  -> Permission Check
  -> Policy Engine
  -> Risk Engine
  -> ALLOW / REQUIRE_APPROVAL / BLOCK
  -> Tool Execution
  -> Audit Event
  -> Replay / Dashboard
```

The agent never executes privileged tools directly — every call goes through
the Tool Gateway.

## Status

This document tracks architecture as it is actually implemented, milestone by
milestone. See `docs/demo-flow.md` for the target product demos and the
project README for current build status.

### Milestone 1 (current)

- Monorepo scaffolding: `apps/web` (Next.js), `apps/api` (FastAPI),
  `packages/*` and `integrations/*` placeholders for later milestones.
- FastAPI backend exposes `/api/health` and `/api/health/db`.
- Next.js frontend calls `/api/health` on load to verify connectivity.
- PostgreSQL wired via `docker-compose`; no domain tables yet.

No agents, tools, policies, risk scoring, or approval workflows exist yet —
those land in later milestones per `docs/demo-flow.md`.
