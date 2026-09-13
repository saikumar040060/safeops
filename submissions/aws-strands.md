# Agents for Humans — paste-ready content

Field limits and exact private form labels remain unverified behind Devpost sign-in. Use the blocks below for corresponding fields; never paste instructions or placeholders as finished answers. [Requirements](REQUIREMENTS.md) · [Recording](RECORDING.md) · [Evidence](EVIDENCE.md)

## Project name

SafeOps + Strands

## Elevator pitch

A Strands support agent that investigates duplicate payments while SafeOps gates every proposed tool action.

## Track

Professional Agents

## Inspiration

Support teams need automation that can investigate a payment issue without quietly authorizing its own refund. We built a Strands agent on SafeOps, our pre-existing authorization platform, to separate an agent's proposal from permission to execute it.

## What it does

The Strands agent reads customer and payment records, identifies a duplicate payment and proposes a refund. Its five tools route through SafeOps' generic API. The gateway checks permission, applies policy where required, assesses contextual risk, and pauses for a human when approval is needed. In the historical PAY-9005 demonstration, a $750 refund reached SUPPORT_REFUND_APPROVAL with LOW risk, score 25. A human approved it; the recorded verification found exactly one refund and 19 audit events, with ToolRequest, ApprovalRequest and ExternalActionRequest all EXECUTED.

## How we built it

The submission-specific component is a real Strands Agent with thin Python tool wrappers over the existing SafeOps client. SafeOps uses FastAPI, PostgreSQL and a Next.js operator dashboard. The historical live agent used Anthropic; Bedrock was blocked by AWS account verification. We do not claim a successful Bedrock run or AgentCore deployment. The architecture diagram shows the model/tool loop, the authorization boundary and the human decision path.

## Challenges we ran into

The model must stop at pending approval instead of retrying a refund. Keeping every tool behind the same gateway makes approval a backend decision rather than an instruction the model can override. AWS account verification also prevented the Bedrock path during the demo, so the verified live run used Anthropic.

## Accomplishments

The historical run exercised real model-driven investigation and an enforced human decision before changing the seeded payment record. Existing security evidence also shows a malicious support-ticket instruction blocked by contextual risk, with a denied tool request and a critical incident. This is a demonstrated scenario, not a claim of universal prompt-injection prevention.

## What we learned

An agent's useful autonomy and a human's authority can coexist when the execution boundary lives outside the model. Low risk does not cancel a policy requirement for human approval.

## What's next

Future work could improve judge-accessible deployment and operational robustness. Those capabilities are not claimed as delivered by this submission.

## Pre-existing work / eligibility disclosure

SafeOps core, its dashboard, authorization engines, audit trail, generic external-agent API and MCP adapter pre-existed this integration. The submission-specific work is integrations/strands/, recorded in commit 6955009 dated September 9, 2026. The entire SafeOps platform is not a from-scratch hackathon build. Commit dates do not establish original authorship dates, and acceptance of this integration on prior work remains subject to the event's new-project rules. The historical demo used Anthropic, not Bedrock. Refunds were changes to seeded demo records, not production payment transfers.

## Built with

Strands Agents SDK, Python, Anthropic, FastAPI, PostgreSQL, Next.js, TypeScript, Docker.

## Required links and private fields

| Field | Value |
|---|---|
| Source repository | https://github.com/saikumar040060/safeops |
| License | https://github.com/saikumar040060/safeops/blob/main/LICENSE |
| Architecture | Upload the reviewed `assets/architecture.png`; after docs push: https://github.com/saikumar040060/safeops/blob/main/submissions/assets/architecture.svg |
| Video | **[MISSING: PUBLIC YOUTUBE OR VIMEO URL, ≤5:00]** |
| AWS Builder ID | **[PRIVATE FORM ONLY: ALREADY-CONFIRMED BUILDER ID EMAIL]** |
| Optional hosted demo | **[NOT AVAILABLE — LEAVE OPTIONAL FIELD EMPTY]** |
| Optional Builder Center blog | **[NOT PROVIDED — LEAVE OPTIONAL FIELD EMPTY]** |

## Testing instructions — current honest status

Source and setup documentation are public in the repository README and docs/strands.md. The recorded demonstration uses seeded demo data and requires a separately configured SafeOps environment plus model access to reproduce. No free, unrestricted judge-accessible running instance has been verified. Testing-access arrangements remain outstanding; do not give judges private production credentials or imply that localhost is publicly reachable. Historical PAY-9005 evidence is summarized in submissions/EVIDENCE.md. A recording of those records must be labeled historical.
