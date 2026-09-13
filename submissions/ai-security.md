# AI Security — provisional, eligibility-blocked copy

Confirmed event association in the authenticated BuilderBase dashboard: [AI Security Hackathon by Hackathons.team](https://luma.com/7a4iutvp), September 13, 2026; [BuilderBase](https://builderbase.com/event/ai-security-hackathon-by-hackathonsteam). Account is accepted in Open Agentic Security but has no team. Form access and cutoff blockers are tracked in REQUIREMENTS.md. **Do not submit this as same-day product development.**

## Project name

SafeOps

## Short description

Runtime authorization for AI tool actions: permit safe work, require human approval, and block malicious context.

## Project / inspiration free-text field

SafeOps addresses the gap between an AI agent proposing an action and a system authorizing it. Its gateway enforces tool permissions, deterministic policy, contextual risk checks and human approval before execution, with an audit trail for the decision.

The historical evidence covers three outcomes: safe reads execute; a $750 seeded refund waits for human approval; and a malicious support ticket is blocked. In the TCK-4837 case, the existing verification reported CRITICAL risk at score 100, a BLOCKED external request, a DENIED tool request and an OPEN critical incident. The email tool was not invoked and customer data was not exported. The email tool itself is a demo no-op, so this proves the gateway decision in the demonstrated case rather than protection of a production email system.

Historical integration evidence includes a real CALL-E confirmation for PAY-9004 and a real Strands/Anthropic investigation for PAY-9005. Each required human approval and was reported to produce one demo refund. The Strands case includes a 19-event audit chain. Bedrock was not successfully used.

Disclosure: SafeOps is pre-existing independent work. This submission-only preparation added documentation and presentation assets, not same-day product functionality. We make no claim that SafeOps was built at this event. We are not claiming use of the Wasmer SDK or a sponsor track in this main-branch baseline. If same-day implementation is required, this package is an exhibition/review candidate only if organizers permit it; otherwise it should not be entered.

## Links

| Field | Value |
|---|---|
| GitHub | https://github.com/saikumar040060/safeops |
| License | Apache-2.0 |
| Video | **[MISSING: VIDEO URL, MAXIMUM 3:00 PER LUMA REMOTE INSTRUCTIONS]** |
| Track | **Open Agentic Security (observed account track; project eligibility still unresolved)** |
| Team/registration identity | **[PRIVATE ACCOUNT FIELDS ONLY; ACCEPTED ACCOUNT, NO TEAM]** |

The provisional 2:45 narration is in RECORDING.md. Hosting rules, exact field limits, final cutoff, and whether historical-record review can meet the working-demo requirement must be checked in the actual event dashboard. A summary-card video cannot be described as a live target demonstration.
