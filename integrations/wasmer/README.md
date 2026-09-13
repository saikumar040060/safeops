# SafeOps / Wasmer Containment Lab

**An allowed tool can still be compromised. Check the action, then contain its execution.**

This is a new Wasmer integration and adversarial demonstration built on September 13,
2026, on top of the pre-existing SafeOps platform. The baseline is commit `e0a27bc`.
The original gateway, policy/risk/approval engines, audit database, and dashboard were
built before the event. They are not claimed as hackathon-day work. The event FAQ permits prior work/context when the demo shows work built on the day.
See the [requirements audit](../../submissions/wasmer-requirements-audit.md) for current instructions.

## See the evidence

- [Actual run results](evidence/results.json): real ToolGateway, Postgres, and Wasmer SDK.
- [Readable evidence report](evidence/report.html): download and open in a browser.
- [Actual-run demo video](evidence/live-demo.mp4): timestamped stdout recording of a fresh
  real gateway/Wasmer run, rendered as terminal video. No slides.
- [Raw timed recording](evidence/live-demo-transcript.json).
- [Captioned evidence walkthrough](evidence/walkthrough.mp4): generated from the verified
  run, not a screen recording of a live agent. Re-run the command below for a live demo.
- [New tool implementation](../../apps/api/app/tools/wasmer_analysis.py)
- [Wasmer guest programs and capability boundary](../../apps/api/app/tools/wasmer_worker.py)
- [New security regression tests](../../apps/api/tests/test_wasmer_analysis.py)

## Run locally

Python 3.13, macOS/Linux arm64 or x86_64, and a local PostgreSQL instance are required.
The official SDK wheel is pinned. First run downloads/compiles the guest Python package;
subsequent runs reuse the local cache. No Wasmer token or LLM API key is needed.

```bash
python3 -m venv .venv
.venv/bin/pip install -r apps/api/requirements.txt -r integrations/wasmer/requirements.txt
# Existing SafeOps Postgres defaults are localhost:5433, safeops/safeops, database safeops.
# Otherwise set SAFEOPS_DEMO_DATABASE_URL to your own local development DB URL.
SAFEOPS_WASMER_CACHE="$PWD/.wasmer" .venv/bin/python integrations/wasmer/demo.py
```

The demo creates a randomly named schema and drops only that schema afterwards.
It never resets the application's existing tables. Credentials are not loaded from
the original checkout. The local database account needs CREATE SCHEMA permission.

## What the demo proves

| Case | Expected observation | Evidence |
|---|---|---|
| Authorized CSV analysis | EXECUTED | Wasmer Python totals two fixture rows to 20.00 |
| Prompt-injected source | BLOCKED | No TOOL_EXECUTED event; regression test asserts worker is never called |
| Denied permission | BLOCKED | No worker starts |
| Compromised-tool fixture | EXECUTED but contained | Guest cannot read an actual synthetic host file or connect to an actual local listener; host positive controls succeed |
| Approval-required analysis | REQUIRES_APPROVAL, then EXECUTED | No execution before approval; a scripted trusted APPROVER identity resolves it, producing one APPROVED_ACTION_EXECUTED event |

The demo uses scripted agent tool proposals and a scripted approval actor. It does not
claim to run a live LLM or a human approval session. It exercises the actual security
services and real sandbox execution. Every target is a local, owned fixture; no real
customer data, external victim, or real payment is involved.

## Design

```mermaid
flowchart LR
    A[Scripted agent proposal] --> G[Existing SafeOps gateway]
    G --> P[Permission / policy / risk]
    P -->|deny| B[Audit: blocked]
    P -->|approval required| H[Trusted approver]
    H --> W
    P -->|allow| W[NEW: Wasmer analysis tool]
    W --> S[SDK worker process]
    S --> V[Wasmer: no mounts, no network]
    V --> R[Result + input hash + audit events]
```

The process boundary lets the host terminate a worker that exceeds 180 seconds;
WebAssembly capabilities provide isolation. The tool accepts only a small CSV and a
fixed program choice. Arbitrary commands, host paths, network flags, and mounts are
rejected by the input schema. The registry entry grants no permission by itself: the
existing database permission check defaults to DENY. SDK failure returns a structured
failure and never retries the operation as host Python.

## Validation

On the development machine, the full backend suite passed **389 tests**, including
10 new regression cases. The real SDK demo passed all 5 scenarios. Timing in
`results.json` is one local run, not a comparative benchmark.

```bash
cd apps/api
# Use a DEDICATED test database: the existing test fixture deletes its tables.
TEST_DATABASE_URL=postgresql+psycopg2://safeops:safeops@127.0.0.1:5433/safeops_wasmer_hackathon_test \
DATABASE_URL=postgresql+psycopg2://safeops:safeops@127.0.0.1:5433/safeops_wasmer_hackathon_test \
../../.venv/bin/pytest -q
```

## Limits

- This contains only the new `wasmer_analyze` tool, not every existing SafeOps tool.
- The denial demo is one known injection fixture; it is not evidence of universal
  prompt-injection detection. Containment remains useful when detection misses.
- Host-file and loopback-network probes demonstrate these specific capability
  restrictions, not a formal proof that every possible escape is impossible.
- Fixed small inputs and a process deadline bound this demo; there is no separately
  configured memory/fuel quota or multi-tenant scheduler. Do not expose it as a public
  arbitrary-code service.
- The registry download uses host networking; guest networking stays disabled.
- Audit ordering is inherited from SafeOps; this extension adds no cryptographic log
  signing or tamper-proof storage. The input hash identifies the input, not trust.
- Remote participation and submission eligibility remain organizer decisions.

## Official SDK sources

[Python SDK documentation](https://docs.wasmer.io/runtime/python/) and
[Wasmer SDK source](https://github.com/wasmerio/wasmer-sdk).
