# SafeOps

SafeOps is a runtime security and governance layer between autonomous AI
agents and the systems they control: agents propose actions, SafeOps
authorizes them (permissions + deterministic policy + risk assessment)
before anything executes.

See `docs/architecture.md` for the full flow, `docs/security-model.md` for
the authorization model, and `docs/demo-flow.md` for the two target demos.

**Status:** Milestone 1 — repo scaffolding, frontend/backend/DB
connectivity. No agents, tools, policy, risk, or approval logic yet.

## Prerequisites

- Node.js 20+ and npm
- Python 3.11+
- Docker and Docker Compose (for the full stack)

## Quick start (Docker)

```bash
cp .env.example .env
docker compose up --build
```

- Frontend: http://localhost:3000
- Backend: http://localhost:8000/api/health
- Postgres: localhost:5433 (user/pass/db: `safeops`) — mapped off the
  default 5432 to avoid clashing with a locally installed Postgres

## Local development (without Docker)

### Backend (FastAPI)

```bash
cd apps/api
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

Requires Postgres reachable at the `DATABASE_URL` in `apps/api/.env`
(defaults to `localhost:5432`, e.g. `docker compose up postgres`).

Run tests and lint:

```bash
pytest
ruff check .
```

### Frontend (Next.js)

```bash
cd apps/web
npm install
npm run dev
```

Uses `NEXT_PUBLIC_API_URL` from `apps/web/.env.local` (defaults to
`http://localhost:8000`).

Run lint and typecheck:

```bash
npm run lint
npx tsc --noEmit
```

## Repository layout

```
apps/
  web/            Next.js frontend
  api/            FastAPI backend
packages/         Shared engines (agent_runtime, tool_gateway, policy_engine,
                  risk_engine, approval_engine, audit_engine, shared) —
                  scaffolded, implemented in later milestones
integrations/     Demo tool APIs and framework adapters (Strands, CALL-E) —
                  scaffolded, implemented in later milestones
infra/            Dockerfiles and infra config
docs/             Architecture, security model, demo flow
```

## Build order

This project is built one milestone at a time — see `docs/architecture.md`
for status and `docs/demo-flow.md` for the target end states. Do not skip
ahead to policy/risk/approval/agent logic until the current milestone is
approved.
