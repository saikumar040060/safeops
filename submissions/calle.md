# CALL-E — paste-ready content

Exact form labels and limits remain unverified behind Devpost sign-in. [Requirements](REQUIREMENTS.md) · [Recording](RECORDING.md) · [Evidence](EVIDENCE.md)

## Project name

SafeOps + CALL-E

## Elevator pitch

CALL-E confirms a customer's refund request by phone; SafeOps requires authorization before the refund executes.

## Inspiration

A phone confirmation establishes what someone asked for, not whether an automated system is authorized to do it. Support staff need that distinction when voice agents propose consequential actions.

## What it does

CALL-E makes an outbound confirmation call and returns a structured result. The adapter submits an action to SafeOps with the transcript marked UNTRUSTED. The historical PAY-9004 demo reached REQUIRES_APPROVAL after a real caller confirmed a $750 duplicate-payment refund. A human then approved the request. The original verification found one refund row and EXECUTED ToolRequest, ApprovalRequest and ExternalActionRequest records. An earlier voicemail outcome caused NO_ACTION. A separate synthetic malicious-transcript test reached BLOCKED with a critical security incident and no tool side effect.

## How we built it

The CALL-E adapter maps a completed call outcome to the pre-existing SafeOps generic API. The gateway enforces permission, policy, risk and approval before tool execution. The historical live call used the official CALL-E CLI path, and the repository also contains the Python SDK adapter. SafeOps is a Python/FastAPI backend with PostgreSQL and a Next.js operator dashboard. No direct path from the call adapter to the refund tool bypasses authorization.

## Challenges we ran into

A hardcoded payment identifier could map a call to the wrong payment. The mismatch was found before approving that request; the pending approval was rejected. Commit ae429cb replaced the hardcoded identifier with explicit scenario values and added regression tests. The corrected PAY-9004 flow was historically verified. No calls or tests were rerun to prepare this submission package.

## Accomplishments

The demonstration connects a real phone confirmation to a separate human authorization decision and an auditable demo refund. PR #519 contributes the project to CALL-E's awesome-phone-call-agents repository. It is open; a merge is not claimed.

## What we learned

Voice content should remain untrusted even when the caller confirms. Correct payment binding and backend approval checks both matter. A voicemail must not silently become permission for a refund.

## What's next

Future work could add richer multi-action call handling and deployment suitable for broader evaluation. This submission implements a single-action polling flow and does not claim those future capabilities.

## Pre-existing work / significant update

SafeOps core, the dashboard, authorization engines, audit trail, generic API and MCP adapter are pre-existing independent work. The submission-specific update is integrations/calle/, recorded in beb41de on September 9, 2026, followed by payment-ID correction and regression tests in ae429cb on September 12. The real call was outbound; this is not an inbound-call implementation. Refunds update seeded SafeOps demo records, not a production payment processor. The malicious voice case used a synthetic transcript, not a real malicious call.

## Built with

CALL-E, Python, FastAPI, PostgreSQL, Next.js, TypeScript, Docker.

## Links and private fields

| Field | Value |
|---|---|
| Required contribution PR URL | https://github.com/CALLE-AI/awesome-phone-call-agents/pull/519 |
| Source repository | https://github.com/saikumar040060/safeops |
| Supporting historical evidence | https://github.com/saikumar040060/safeops/blob/main/submissions/EVIDENCE.md — available after docs push |
| Video | **[MISSING: PUBLIC YOUTUBE OR VIMEO URL, STRICTLY UNDER 3:00]** |
| CALL-E account email | **[PRIVATE FORM ONLY: ALREADY-CONFIRMED ACCOUNT EMAIL]** |
| Optional functional app URL | **[NOT AVAILABLE — LEAVE OPTIONAL FIELD EMPTY]** |

## Testing instructions — current honest status

The repository README and docs/calle.md provide installation and configuration documentation. Reproduction requires CALL-E access and a separately configured SafeOps demo environment. No unrestricted free running test instance has been verified. Do not expose private tokens or phone numbers in public test instructions. The package supplies historical confirmation and approval evidence; it does not start another call or refund.
