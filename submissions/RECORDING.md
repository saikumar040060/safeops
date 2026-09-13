# Recording scripts — existing evidence only

No calls, model runs, approvals, refunds, demo scripts, seed scripts or application mutations. These are screen-recording instructions, not commands to run the product. Use a clean browser window with notifications hidden. Never show login/token fields, address-book data, terminal history, account menus or provider IDs. Read the exact narration in quotes; identifiers may be spoken naturally (for example, “payment nine thousand five”).

Use the reviewed PNG cards in `assets/` (title, strands, calle, block, voice, disclosure), or `assets/evidence.html`, for sanitized title/evidence cards and `assets/architecture.svg` for the existing architecture. The cards are newly typeset historical summaries, **not original screenshots**. Keep their historical label visible. Where the shot calls for retained original footage or completed records, use only genuine existing evidence; if unavailable, show the labeled summary and retain the working-demo-evidence blocker. Do not fabricate pending-state screens from executed records. Any approval transition must be old footage/audit review, never a new click.

Timing assumes roughly 125–140 spoken words/minute. Each slot includes a reading hold and a one-second hard cut. Keep the final encoded duration within the stated target, including titles, fades and silence. No music or third-party logos are necessary.

## 1. Agents for Humans — 4:50 target; verified maximum 5:00

### 0:00–0:35 — title card and audience

Screen: evidence card “SafeOps”; show the problem and historical-evidence label. Transition: hard cut to architecture at 0:35.

“A support agent can investigate a payment problem, but deciding to issue a refund should not automatically give it permission to do so. SafeOps plus Strands separates those decisions. This is for support teams that want useful automation while keeping control over consequential actions. I will show existing evidence from our completed demonstration; this recording does not place a new call or execute another refund.”

### 0:35–1:15 — architecture

Screen: full architecture, then zoom the Strands → API → gateway route. Point to model loop, output and human path. Cut at 1:15.

“The user gives the Strands agent a task through the command line. The model reasons, calls tools and receives results. Our five tool wrappers submit requests through the SafeOps API. The gateway enforces permission, policy where needed, contextual risk and human approval. A result returns to the agent, while decisions are recorded for operator review. The historical run used Anthropic. Bedrock was blocked by account verification, and we are not claiming an AgentCore deployment.”

### 1:15–1:40 — existing source

Screen: read-only `integrations/strands/tools.py`, `_submit` and `refund_payment` docstring, with no terminal. Cut to PAY-9005 card.

“These are thin tool wrappers over the shared SafeOps client. They do not directly invoke the payment implementation. The refund wrapper also tells the agent to stop when approval is pending. That instruction helps the agent communicate clearly; the backend gateway is what actually prevents execution before approval.”

### 1:40–2:20 — historical investigation

Screen: retained original Strands trace if available; otherwise clearly labeled PAY-9005 historical card. Slowly point to reads and proposed refund. Cut at 2:20.

“In the completed live-model demonstration, the Strands agent read the customer and payment records and identified payment nine thousand five as the outstanding duplicate. It proposed a seven hundred fifty dollar refund. The existing verification records the investigation and the requested action. These are seeded SafeOps payment records. The demonstration changed the demo database; it was not a transfer through a production payment processor.”

### 2:20–3:00 — historical approval decision

Screen: retained audit or historical card showing policy, LOW/25, REQUIRES_APPROVAL. Do not show an active approval button. Cut at 3:00.

“The matched policy was support refund approval. Risk was low, with a score of twenty-five, but that did not remove the policy requirement. SafeOps returned requires approval and paused the action. The model could propose the refund, but a human had to authorize it. Reviewing this record lets us explain the pause without changing the system or creating another approval request.”

### 3:00–3:40 — completed result and audit

Screen: retained final record if accessible; otherwise historical audit list in EVIDENCE.md/PAY-9005 card. Point to approval then execution, and one refund. Cut at 3:40.

“After the historical human approval, the tool request, approval request and external action request all reached executed. The original database verification found exactly one refund row. The nineteen-event audit sequence connects receipt, permission, policy and risk checks to the approval and completed action. That is evidence for this demonstrated scenario. We do not present it as a universal exactly-once guarantee across every possible deployment.”

### 3:40–4:15 — existing malicious BLOCK evidence

Screen: BLOCK card or retained incident/audit record; show CRITICAL/100 and DENIED. Cut at 4:15.

“The existing security demonstration supplies a second outcome. A support ticket tried to redirect an action toward exporting customer data and sending it externally. Contextual risk marked it critical and blocked the external request. The tool request was denied and a security incident was recorded. This is historical gateway evidence, not a newly run Strands attack test, and it does not establish that every prompt injection will be caught.”

### 4:15–4:50 — disclosure and close

Screen: disclosure card, public repo/license and Strands adapter commit. Hold to 4:49, hard end 4:50.

“SafeOps core, its dashboard and generic integration layer are pre-existing independent work. The submission-specific component is the Strands adapter, recorded in September. We disclose that boundary and the Anthropic provider openly. The repository is public under Apache two point zero. The result is a support workflow where the agent investigates, the backend controls execution, and the operator can review the decision trail.”

## 2. CALL-E — 2:45 target; strictly below 3:00

### 0:00–0:20 — title and problem

Screen: CALL-E title card, historical label. Cut at 0:20.

“A phone confirmation tells us what a customer wants. It does not authorize a refund. SafeOps plus CALL-E connects a real outbound confirmation call to a separate backend approval decision. This video reviews the completed demonstration.”

### 0:20–0:40 — integration boundary

Screen: existing `submit_call_outcome_to_safeops` source or architecture. Cut at 0:40.

“CALL-E returns a structured outcome. The adapter sends it through SafeOps with the transcript marked untrusted. Permission, policy and contextual risk determine whether the proposed action can proceed or must wait for a human.”

### 0:40–1:05 — genuine historical confirmation

Screen: sanitized retained transcript excerpt in EVIDENCE.md. If an original authorized recording exists, use it within the same slot; do not synthesize caller audio. Cut at 1:05.

“The retained transcript documents a real caller confirming a seven hundred fifty dollar duplicate-payment refund, then confirming again. We have omitted private provider identifiers. This was an outbound call. We are showing the transcript from that call, not dialing again.”

### 1:05–1:30 — approval pause

Screen: PAY-9004 historical evidence, then relevant retained audit if available. Cut at 1:30.

“For payment nine thousand four, the result was requires approval. The caller's words remained untrusted source context. Confirmation alone could not execute the refund. The historical record shows a human approval before the request completed.”

### 1:30–1:55 — result and correction

Screen: EXECUTED / one refund and ae429cb. Do not click approval. Cut at 1:55.

“The original verification found one demo refund and executed request records. A prior payment-ID mismatch was rejected before approval and corrected with regression tests. This refund changed seeded demo records, not a production payment account.”

### 1:55–2:20 — no-action and BLOCK

Screen: voicemail NO_ACTION summary, then malicious-transcript card. Cut at 2:20.

“An earlier voicemail produced no action because there was no live confirmation. Separately, a synthetic malicious transcript was blocked with a critical incident and no tool side effect. That security case was not another real phone call.”

### 2:20–2:45 — contribution and disclosure

Screen: PR #519 content cropped to title/open badge and project entry, then disclosure card. End at 2:45.

“The contribution is linked in open pull request five nineteen. SafeOps core is pre-existing; the CALL-E adapter and payment-binding correction are the submission-specific update. The public repository is Apache licensed. Voice intent and execution authority remain separate, with a record of the decision.”

## 3. AI Security — provisional 2:45; verified remote maximum 3:00

The official event emphasizes same-day progress and a working demo. This historical review does not establish compliance. Use only if the event permits the disclosed scope; no new workflow is authorized. No sponsor integration is claimed.

### 0:00–0:20 — disclosure first

Screen: “Pre-existing SafeOps — historical evidence review.” Cut at 0:20.

“SafeOps is a pre-existing runtime authorization project. Today I am presenting historical security evidence, not claiming new same-day product work. An AI agent can propose an action; the gateway decides whether its tool may execute.”

### 0:20–0:45 — boundary

Screen: architecture, zoom gateway and audit. Cut at 0:45.

“Permission establishes whether the agent can use a tool. Policy can require human review, and risk examines the untrusted context driving the request. Approved actions reach tools; blocked requests do not. Decisions are recorded for inspection.”

### 0:45–1:05 — ALLOW

Screen: historical safe-read card or existing completed read record. Cut at 1:05.

“The first historical path is a safe customer read. It executed without approval after the relevant checks. Authorization should preserve useful work when the request is permitted and its context does not require escalation.”

### 1:05–1:30 — human approval

Screen: PAY-9005 historical policy/result, not an active control. Cut at 1:30.

“The second path is a seven hundred fifty dollar seeded refund. Policy required a human even with low assessed risk. The completed Strands demonstration reports one refund and nineteen audit events, with execution occurring after approval.”

### 1:30–2:05 — malicious evidence

Screen: BLOCK card; emphasize source → signals → DENIED. Cut at 2:05.

“The third path starts with a malicious support ticket asking for customer-data export and external delivery. The email tool was ordinarily allowed, but contextual risk detected injection, exfiltration and external communication. The request was blocked at critical risk, score one hundred. A critical incident was recorded and the tool request was denied. The email implementation never ran in this case.”

### 2:05–2:25 — limitations

Screen: zero-side-effect table and limits. Cut at 2:25.

“The email tool is a demo no-op, and refunds use seeded records. These results demonstrate the gateway's decisions in specific scenarios. They are not a benchmark of every attack, a production money transfer, or evidence of universal protection.”

### 2:25–2:45 — close

Screen: public repo and pre-existing disclosure. End at 2:45.

“The same existing boundary serves internal agents, MCP, Strands and CALL-E. The public repository is Apache licensed. No Wasmer integration or same-day development is claimed in this submission. The evidence is available for honest review of what SafeOps already does.”

## Final export checks

- Agents for Humans: target 4:50, maximum 5:00 including silence/titles.
- CALL-E: target 2:45; do not export at 3:00.
- AI Security: target 2:45, maximum 3:00, pending eligibility and form confirmation.
- Review every frame, spoken line, caption and thumbnail for private identity/token exposure.
- Publish the two Devpost videos as **public** YouTube/Vimeo, then verify playback logged out. Do not substitute unlisted without rule clarification.
- Record the real encoded durations and final URLs in CHECKLIST.md. Until then, video requirements remain incomplete.
