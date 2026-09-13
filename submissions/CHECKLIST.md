# Submission readiness checklist

Requirements below for **Agents for Humans** and **CALL-E** were pulled
directly from their live Devpost rules pages during preparation (sources
linked). Nothing here is guessed. **This file does not submit anything
and does not change repo visibility or add a license** — both remain
exactly as they are until explicitly approved.

---

## 1. Agents for Humans (AWS Strands)

Source: [agentsforhumans.devpost.com/rules](https://agentsforhumans.devpost.com/rules)
**Deadline: September 14, 2026, 5:00 PM PDT**

| Requirement | Status | Notes |
|---|---|---|
| Newly built agent on Strands Agents SDK, does real work end to end | ✅ Done | `integrations/strands/` — real `Agent`, 5 tools, verified live end to end |
| **Repository public** (GitHub/GitLab/Bitbucket) | ❌ **Blocking — repo is currently PRIVATE** | Requires your explicit approval to flip; not done |
| **MIT or Apache license visible at repo top level** | ❌ **Blocking — no LICENSE file exists** | You previously said "skip for now"; requires your explicit approval + choice before this hackathon can be submitted |
| README | ✅ Done | Root `README.md` + `submissions/aws-strands.md` |
| Architecture diagram | ✅ Done | Mermaid sequence diagram in `submissions/aws-strands.md` |
| Text description of features/functionality | ✅ Done | "README (submission page copy)" section |
| Video, ≤5 minutes, public on YouTube/Vimeo, covers problem/audience/why-it-matters | ⏳ Script ready, **not recorded/uploaded** | Timed script in `submissions/aws-strands.md` |
| AWS Builder ID | ✅ Confirmed | Registered under saikumar040060@gmail.com |
| Testing access for judges (free; credentials if private) | Blocked on repo-visibility decision above | Moot once repo is public |
| Pre-existing-code disclosure | ✅ Done | Explicit section in `submissions/aws-strands.md`; **flag**: rules say "all work must be created during the submission period" — SafeOps core predates it substantially. Disclosure is written honestly; whether that framing satisfies this specific hackathon's judges is your call, not something I can decide. |
| Third-party SDK authorization | ✅ OK | Strands Agents SDK is Apache-2.0 licensed, no additional authorization needed |
| Register + create submission on agentsforhumans.devpost.com | ❌ Not done | External account action, outside this repo |

---

## 2. CALL-E: Your Code Is Calling

Source: [call-e.devpost.com/rules](https://call-e.devpost.com/rules)
**Deadline: September 14, 2026, 11:45 PM SGT**

| Requirement | Status | Notes |
|---|---|---|
| Functional software using CALL-E API/SDK | ✅ Done, live-verified | Two real outbound calls, full approval → execution loop |
| **Open a PR to `github.com/CALLE-AI/awesome-phone-call-agents`** | ❌ **Not done** | Full checklist in `submissions/calle.md` "PR checklist" section — this repo's own README hasn't even been inspected yet |
| Provide the PR URL on the submission form | ❌ Not done | Depends on the PR above |
| Video, under 3 minutes, public on YouTube/Vimeo | ⏳ Script ready, **not recorded/uploaded** | Timed script in `submissions/calle.md` |
| No third-party trademarks/copyrighted music in video | ⚠️ Keep in mind when recording | Not a code issue |
| Written description | ✅ Done | `submissions/calle.md` |
| Testing access (free; credentials if private) | Blocked on repo-visibility decision | This hackathon's rules don't explicitly require the *main* repo public the way Strands' does — only the PR target repo is required to be public. Confirm whether judges also need direct access to `saikumar/safeops`. |
| Email address associated with CALL-E account | ✅ Confirmed | saikumar040060@gmail.com |
| Disclosure: "newly created or significantly updated during submission period" | ✅ Reasonable | `integrations/calle/` genuinely was built/updated now; less strict wording than Strands' hackathon |
| IP rights / third-party authorization | ✅ OK | Your own CALL-E account/API access |
| Register + submit on call-e.devpost.com | ❌ Not done | External account action |

---

## 3. AI Security hackathon

**Could not find a specific, confirmed hackathon page matching "AI
Security" with a Sep 14 2026-ish deadline** — searched Devpost broadly;
nothing matched both the name and your stated timeline. Before I can
check real requirements against this one, I need the actual platform/URL
from you.

In the meantime, the assets are prepared to a generic, solid standard:

| Asset | Status |
|---|---|
| Safe ALLOW path, captured live | ✅ Done |
| $750 approval path, captured live (approve → executes exactly once) | ✅ Done |
| Malicious TCK-4837 → CRITICAL/BLOCK path, captured live | ✅ Done |
| Zero-side-effect proof | ✅ Done — dedicated section in `submissions/ai-security.md` |
| Architecture diagram | ✅ Done — Mermaid flowchart in `submissions/ai-security.md` |
| Demo script | ✅ Done |
| Platform-specific requirements (video length, repo visibility, license, PR targets, etc.) | ❓ **Unknown until you provide the actual hackathon URL/name** |

---

## Cross-cutting items that affect more than one submission

- **Repository visibility**: private today. Agents for Humans explicitly
  requires public + license; CALL-E's own repo requirement is narrower
  (the PR target repo, not necessarily yours). If you make it public for
  Strands, that also satisfies CALL-E's judging-access needs for free.
  **Not changed — needs your explicit go-ahead**, per your standing
  instruction.
- **License**: needed for Agents for Humans specifically (MIT or
  Apache), not clearly required by CALL-E. You previously chose Apache
  2.0, then said "skip for now." **Not added — needs your explicit
  go-ahead** on whether/which license, before that hackathon can be
  submitted.
- **AWS Builder ID** and **CALL-E account email** — both confirmed
  (saikumar040060@gmail.com for each).
- **Video recording/upload** is the single biggest remaining gap across
  both confirmed hackathons — both scripts are ready, neither has been
  recorded.
