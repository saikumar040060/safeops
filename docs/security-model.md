# SafeOps Security Model

## Core rule

The LLM can propose an action. Only SafeOps can authorize it.

```
LLM risk analysis
+ deterministic policy
+ permissions
+ context
= decision
```

Never let "the LLM says this is safe" be the final authorization. Policy
decisions must be deterministic and reproducible; the risk engine's
LLM-based contextual classification is a signal into that decision, never
the decision itself.

## Layers (introduced in later milestones)

- **Permissions** — per-agent, per-tool ALLOW / CONDITIONAL / DENY.
- **Policy Engine** — deterministic rules (e.g. refund amount thresholds)
  returning `{decision, reason, matched_policy, risk_level}`.
- **Risk Engine** — detects prompt injection, scope deviation, sensitive
  data access, privilege escalation, and similar signals; deterministic
  rules first, LLM classification second.
- **Approval Engine** — pauses execution and asks a human when policy or
  risk requires it; resumes on approval.
- **Audit Engine** — immutable, ordered event log for every execution, used
  for the Security Center and Replay UI.

Not implemented in Milestone 1: none of the above layers exist yet. The
Tool Gateway does not exist yet either — see `docs/architecture.md` for
current status.
