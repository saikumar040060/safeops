# Wasmer entry: requirements audit

Checked September 13, 2026 against the actual event instructions, not the unrelated
AWS Strands or CALL-E rules in the historical checklist.

## Official sources

- [Luma event and remote instructions](https://luma.com/7a4iutvp): remote submission
  consists of a video (maximum three minutes), an open-source GitHub repository linked
  in the submission, and a free-text project description.
- [Builderbase event FAQ](https://builderbase.com/track-dashboard/wasmer-sdk/event-site):
  prior work/context is allowed, but the demo should show what was built on the day.
- [Wasmer track rubric](https://builderbase.com/track-dashboard/wasmer-sdk/overview):
  real authorized target (30%), technical depth (25%), originality (20%), shock factor
  (15%), progress on the day (10%); show the project running with Wasmer SDK and explain
  its use. These are judging dimensions, not scores we can award ourselves.

## Requirement-by-requirement

| Requirement | Verified status | Evidence / remaining action |
|---|---|---|
| Agentic security project | Ready | Gateway controls plus Wasmer tool containment |
| Actual Wasmer SDK use | Ready | SDK 0.2.1 runs Python WASIX 3.13.18; fixed files; no mounts/network |
| Working demonstration on authorized target | Ready locally | Five real cases, local synthetic canary and local listener with positive controls |
| Remote video ≤3 minutes, showing what was built | Ready: 68.81 seconds | `live-demo.mp4` renders the timestamped stdout capture of a fresh real run. It is not an app screen capture. |
| Open-source GitHub repository | Ready | Public branch and Apache-2.0 LICENSE |
| Repository linked in submission | Not yet confirmed | URL is saved in team description; no dedicated submission field visible |
| Video attached/linked in submission | Not yet confirmed | Public repository asset linked from entry README; no dedicated submission field visible |
| Free-text project description | Ready | Team description plus full submission draft; actual submission field not yet visible |
| Work built during event | Disclosed | New Wasmer extension and demo, with baseline e0a27bc; core predates event |
| Team size 1–5 | Ready | Satya Sai Kumar, one member |
| Tests and reproducibility | Ready | 389 backend tests; live integration assertions; setup README |
| Final submit receipt | Missing | No final submission performed or receipt received |

## Material findings

The official Luma page now contains remote submission instructions. A Zoom/Meet link
is not listed as a prerequisite for submitting the video. The earlier Help Desk request
for a joining link is therefore not a reason by itself to delay preparing the entry.

The FAQ explicitly permits context and prior work. Continue to demonstrate and disclose
only today's new contribution; that is more precise than claiming the full SafeOps
platform started today. Judges retain eligibility/scoring authority.

The previous 72-second walkthrough contains explanatory evidence slides. Use the new
actual-run video for the submission because it directly shows SDK execution results.
Both the CLI requests and approver identity are scripted, clearly disclosed.

Builderbase still routes Submit Work directly to a locking confirmation, with no visible
repository/video/free-text submission fields even after refresh. This conflicts with
Luma's description of the submission form. Do not equate a saved team description with
a complete project submission. Resolve the missing fields or obtain organizer instructions
before claiming all requirements are fulfilled.

The sidebar timer and overview countdown differ. The page displays 22:30 September 13
without a timezone; Luma's event schedule is Pacific. Do not infer a precise submission
deadline from these conflicting timers.
