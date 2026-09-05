from app.models import Agent, Execution, Policy, Tool
from app.models.enums import ExecutionStatus, PolicyAction
from app.services.policy_engine import policy_engine


def _agent(db, name) -> Agent:
    return db.query(Agent).filter_by(name=name).one()


def _tool(db, name) -> Tool:
    return db.query(Tool).filter_by(name=name).one()


def _execution(db, agent) -> Execution:
    execution = Execution(agent_id=agent.id, objective="test", status=ExecutionStatus.RUNNING)
    db.add(execution)
    db.commit()
    db.refresh(execution)
    return execution


def _evaluate(db, agent, tool, arguments):
    execution = _execution(db, agent)
    return policy_engine.evaluate(
        agent=agent, tool=tool, arguments=arguments, execution=execution, db=db
    )


def test_no_matching_policy_fails_closed(seeded_db):
    agent = _agent(seeded_db, "support-agent")
    tool = _tool(seeded_db, "get_payments")  # no policies configured for this tool

    result = _evaluate(seeded_db, agent, tool, {"customer_id": "CUST-1001"})

    assert result.decision == PolicyAction.BLOCK
    assert "NO_MATCHING_POLICY" in result.reason
    assert result.matched_policy is None


def test_disabled_policy_is_ignored(seeded_db):
    agent = _agent(seeded_db, "support-agent")
    tool = _tool(seeded_db, "refund_payment")

    seeded_db.add(
        Policy(
            policy_key="TEST_DISABLED_ALLOW_ALL",
            name="disabled catch-all",
            agent_type="support",
            tool_id=tool.id,
            priority=999,
            enabled=False,
            action=PolicyAction.ALLOW,
            conditions={},
        )
    )
    seeded_db.commit()

    # Only the disabled policy would match unconditionally; the real seeded
    # tiered policies still apply underneath it.
    result = _evaluate(
        seeded_db, agent, tool, {"amount": "50.00", "payment_id": "PAY-1", "reason": "x"}
    )
    assert result.decision == PolicyAction.ALLOW
    assert result.matched_policy == "SUPPORT_REFUND_AUTONOMOUS"


def test_higher_priority_policy_wins(seeded_db):
    agent = _agent(seeded_db, "devops-agent")
    tool = _tool(seeded_db, "deploy_staging")

    seeded_db.add(
        Policy(
            policy_key="TEST_HIGH_PRIORITY_BLOCK",
            name="high priority block",
            agent_type="devops",
            tool_id=tool.id,
            priority=500,
            enabled=True,
            action=PolicyAction.BLOCK,
            conditions={},
        )
    )
    seeded_db.commit()

    result = _evaluate(seeded_db, agent, tool, {"service_name": "checkout-service", "version": "1"})

    assert result.decision == PolicyAction.BLOCK
    assert result.matched_policy == "TEST_HIGH_PRIORITY_BLOCK"


def test_exact_agent_policy_beats_agent_type_policy(seeded_db):
    agent = _agent(seeded_db, "devops-agent")
    tool = _tool(seeded_db, "deploy_production")

    # Pin an exact-agent override that ALLOWS production deploys for this one
    # agent, even though the agent_type-scoped seed policy requires approval.
    seeded_db.add(
        Policy(
            policy_key="TEST_EXACT_AGENT_ALLOW",
            name="exact agent override",
            agent_id=agent.id,
            tool_id=tool.id,
            priority=100,
            enabled=True,
            action=PolicyAction.ALLOW,
            conditions={},
        )
    )
    seeded_db.commit()

    result = _evaluate(
        seeded_db, agent, tool, {"service_name": "checkout-service", "version": "1"}
    )

    assert result.decision == PolicyAction.ALLOW
    assert result.matched_policy == "TEST_EXACT_AGENT_ALLOW"


def test_non_matching_exact_agent_policy_falls_through_to_agent_type(seeded_db):
    agent = _agent(seeded_db, "devops-agent")
    tool = _tool(seeded_db, "deploy_production")

    # An exact-agent policy exists for this tool, but its conditions never
    # match this request. A narrow, non-applicable override must not hide
    # the broader agent_type policy that does apply -- evaluation falls
    # through to the agent_type rank (seeded: REQUIRE_APPROVAL).
    seeded_db.add(
        Policy(
            policy_key="TEST_EXACT_AGENT_NEVER_MATCHES",
            name="exact agent, impossible condition",
            agent_id=agent.id,
            tool_id=tool.id,
            priority=100,
            enabled=True,
            action=PolicyAction.ALLOW,
            conditions={
                "all": [{"field": "arguments.version", "operator": "eq", "value": "never"}]
            },
        )
    )
    seeded_db.commit()

    result = _evaluate(
        seeded_db, agent, tool, {"service_name": "checkout-service", "version": "1"}
    )

    assert result.decision == PolicyAction.REQUIRE_APPROVAL
    assert result.matched_policy == "DEVOPS_PRODUCTION_DEPLOY"


def test_no_rank_matches_falls_closed(seeded_db):
    agent = _agent(seeded_db, "devops-agent")
    tool = _tool(seeded_db, "deploy_production")

    # Same non-matching exact-agent override, but this time disable the
    # agent_type seed policy too so no rank ever matches.
    seeded_db.add(
        Policy(
            policy_key="TEST_EXACT_AGENT_NEVER_MATCHES_2",
            name="exact agent, impossible condition",
            agent_id=agent.id,
            tool_id=tool.id,
            priority=100,
            enabled=True,
            action=PolicyAction.ALLOW,
            conditions={
                "all": [{"field": "arguments.version", "operator": "eq", "value": "never"}]
            },
        )
    )
    seeded_db.query(Policy).filter_by(policy_key="DEVOPS_PRODUCTION_DEPLOY").update(
        {"enabled": False}
    )
    seeded_db.commit()

    result = _evaluate(
        seeded_db, agent, tool, {"service_name": "checkout-service", "version": "1"}
    )

    assert result.decision == PolicyAction.BLOCK
    assert "NO_MATCHING_POLICY" in result.reason


def test_conflicting_equal_priority_policies_fail_closed(seeded_db):
    agent = _agent(seeded_db, "devops-agent")
    tool = _tool(seeded_db, "deploy_staging")

    seeded_db.add_all(
        [
            Policy(
                policy_key="TEST_CONFLICT_ALLOW",
                name="conflict allow",
                agent_type="devops",
                tool_id=tool.id,
                priority=500,
                enabled=True,
                action=PolicyAction.ALLOW,
                conditions={},
            ),
            Policy(
                policy_key="TEST_CONFLICT_BLOCK",
                name="conflict block",
                agent_type="devops",
                tool_id=tool.id,
                priority=500,
                enabled=True,
                action=PolicyAction.BLOCK,
                conditions={},
            ),
        ]
    )
    seeded_db.commit()

    result = _evaluate(seeded_db, agent, tool, {"service_name": "checkout-service", "version": "1"})

    assert result.decision == PolicyAction.BLOCK
    assert "POLICY_CONFLICT" in result.reason
    assert result.matched_policy is None


def test_equal_priority_same_action_is_not_a_conflict(seeded_db):
    agent = _agent(seeded_db, "devops-agent")
    tool = _tool(seeded_db, "deploy_staging")

    seeded_db.add_all(
        [
            Policy(
                policy_key="TEST_DUP_A",
                name="dup a",
                agent_type="devops",
                tool_id=tool.id,
                priority=500,
                enabled=True,
                action=PolicyAction.BLOCK,
                conditions={},
            ),
            Policy(
                policy_key="TEST_DUP_B",
                name="dup b",
                agent_type="devops",
                tool_id=tool.id,
                priority=500,
                enabled=True,
                action=PolicyAction.BLOCK,
                conditions={},
            ),
        ]
    )
    seeded_db.commit()

    result = _evaluate(seeded_db, agent, tool, {"service_name": "checkout-service", "version": "1"})

    assert result.decision == PolicyAction.BLOCK
    # deterministic tie-break: lexicographically smallest policy_key
    assert result.matched_policy == "TEST_DUP_A"


def test_malformed_condition_missing_keys_fails_closed(seeded_db):
    agent = _agent(seeded_db, "support-agent")
    tool = _tool(seeded_db, "get_support_ticket")

    seeded_db.add(
        Policy(
            policy_key="TEST_MALFORMED",
            name="malformed condition",
            agent_type="support",
            tool_id=tool.id,
            priority=100,
            enabled=True,
            action=PolicyAction.ALLOW,
            conditions={"all": [{"field": "arguments.ticket_id"}]},  # missing operator/value
        )
    )
    seeded_db.commit()

    result = _evaluate(seeded_db, agent, tool, {"ticket_id": "TCK-4820"})

    assert result.decision == PolicyAction.BLOCK
    assert "POLICY_EVALUATION_ERROR" in result.reason


def test_unsupported_operator_fails_closed(seeded_db):
    agent = _agent(seeded_db, "support-agent")
    tool = _tool(seeded_db, "get_support_ticket")

    seeded_db.add(
        Policy(
            policy_key="TEST_BAD_OPERATOR",
            name="unsupported operator",
            agent_type="support",
            tool_id=tool.id,
            priority=100,
            enabled=True,
            action=PolicyAction.ALLOW,
            conditions={
                "all": [
                    {
                        "field": "arguments.ticket_id",
                        "operator": "regex",
                        "value": ".*",
                    }
                ]
            },
        )
    )
    seeded_db.commit()

    result = _evaluate(seeded_db, agent, tool, {"ticket_id": "TCK-4820"})

    assert result.decision == PolicyAction.BLOCK
    assert "POLICY_EVALUATION_ERROR" in result.reason


def test_missing_argument_cannot_accidentally_authorize(seeded_db):
    agent = _agent(seeded_db, "support-agent")
    tool = _tool(seeded_db, "refund_payment")

    # Bypasses the tool's own pydantic validation (which would normally
    # reject a missing amount) to exercise the engine's own fail-closed
    # handling of a missing field.
    result = _evaluate(
        seeded_db, agent, tool, {"payment_id": "PAY-9003", "reason": "no amount supplied"}
    )

    assert result.decision == PolicyAction.BLOCK
    assert "POLICY_EVALUATION_ERROR" in result.reason


def test_evaluator_cannot_execute_arbitrary_code(seeded_db):
    agent = _agent(seeded_db, "support-agent")
    tool = _tool(seeded_db, "get_support_ticket")

    payload = "__import__('os').system('touch /tmp/safeops_policy_engine_pwned')"
    seeded_db.add(
        Policy(
            policy_key="TEST_NO_CODE_EXEC",
            name="literal string comparison only",
            agent_type="support",
            tool_id=tool.id,
            priority=100,
            enabled=True,
            action=PolicyAction.ALLOW,
            conditions={
                "all": [{"field": "arguments.ticket_id", "operator": "eq", "value": payload}]
            },
        )
    )
    seeded_db.commit()

    result = _evaluate(seeded_db, agent, tool, {"ticket_id": "TCK-4820"})

    # The payload is compared as a literal string and never matches; no code
    # runs, and evaluation fails closed to NO_MATCHING_POLICY.
    assert result.decision == PolicyAction.BLOCK
    assert "NO_MATCHING_POLICY" in result.reason


def test_in_operator(seeded_db):
    agent = _agent(seeded_db, "support-agent")
    tool = _tool(seeded_db, "get_support_ticket")

    seeded_db.add(
        Policy(
            policy_key="TEST_IN_OPERATOR",
            name="in operator",
            agent_type="support",
            tool_id=tool.id,
            priority=100,
            enabled=True,
            action=PolicyAction.ALLOW,
            conditions={
                "all": [
                    {
                        "field": "arguments.ticket_id",
                        "operator": "in",
                        "value": ["TCK-4820", "TCK-4837"],
                    }
                ]
            },
        )
    )
    seeded_db.commit()

    matched = _evaluate(seeded_db, agent, tool, {"ticket_id": "TCK-4820"})
    assert matched.decision == PolicyAction.ALLOW

    unmatched = _evaluate(seeded_db, agent, tool, {"ticket_id": "TCK-9999"})
    assert unmatched.decision == PolicyAction.BLOCK
    assert "NO_MATCHING_POLICY" in unmatched.reason


def test_engine_evaluation_is_read_only(seeded_db):
    """The engine must never write PolicyDecision or mutate ToolRequest --
    that is the Tool Gateway's job, kept separate so evaluation stays a pure
    function of (agent, tool, arguments, current policy rows)."""
    from app.models import PolicyDecision

    agent = _agent(seeded_db, "support-agent")
    tool = _tool(seeded_db, "refund_payment")

    _evaluate(seeded_db, agent, tool, {"amount": "50.00", "payment_id": "PAY-1", "reason": "x"})

    assert seeded_db.query(PolicyDecision).count() == 0
