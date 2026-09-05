from app.core.seed import (
    SEED_AGENTS,
    SEED_DEPLOYMENTS,
    SEED_PAYMENTS,
    SEED_PERMISSIONS,
    SEED_POLICIES,
    SEED_SERVICE_LOGS,
    SEED_SUPPORT_TICKETS,
    SEED_TOOLS,
    seed,
)
from app.models import (
    Agent,
    AgentToolPermission,
    Customer,
    Deployment,
    Payment,
    Policy,
    Service,
    ServiceLog,
    SupportTicket,
    Tool,
)


def test_seed_creates_expected_agents_and_tools(db_session):
    seed(db_session)

    assert db_session.query(Agent).count() == len(SEED_AGENTS)
    assert db_session.query(Tool).count() == len(SEED_TOOLS)
    assert db_session.query(Customer).count() == 1
    assert db_session.query(Payment).count() == len(SEED_PAYMENTS)
    assert db_session.query(SupportTicket).count() == len(SEED_SUPPORT_TICKETS)
    assert db_session.query(Service).count() == 1
    assert db_session.query(Deployment).count() == len(SEED_DEPLOYMENTS)
    assert db_session.query(ServiceLog).count() == len(SEED_SERVICE_LOGS)
    assert db_session.query(Policy).count() == len(SEED_POLICIES)

    agent_names = {a.name for a in db_session.query(Agent).all()}
    tool_names = {t.name for t in db_session.query(Tool).all()}
    assert agent_names == {a["name"] for a in SEED_AGENTS}
    assert tool_names == {t["name"] for t in SEED_TOOLS}


def test_seed_is_idempotent(db_session):
    seed(db_session)
    seed(db_session)
    seed(db_session)

    assert db_session.query(Agent).count() == len(SEED_AGENTS)
    assert db_session.query(Tool).count() == len(SEED_TOOLS)
    assert db_session.query(Customer).count() == 1
    assert db_session.query(Payment).count() == len(SEED_PAYMENTS)
    assert db_session.query(SupportTicket).count() == len(SEED_SUPPORT_TICKETS)
    assert db_session.query(Service).count() == 1
    assert db_session.query(Deployment).count() == len(SEED_DEPLOYMENTS)
    assert db_session.query(ServiceLog).count() == len(SEED_SERVICE_LOGS)
    assert db_session.query(AgentToolPermission).count() == len(SEED_PERMISSIONS)
    assert db_session.query(Policy).count() == len(SEED_POLICIES)


def test_seed_policies_match_expected_keys(db_session):
    seed(db_session)

    policy_keys = {p.policy_key for p in db_session.query(Policy).all()}
    assert policy_keys == {p["policy_key"] for p in SEED_POLICIES}

    tool_names = {t.id: t.name for t in db_session.query(Tool).all()}
    actual = {
        (p.policy_key, p.agent_type, tool_names[p.tool_id], p.action.value): p.enabled
        for p in db_session.query(Policy).all()
    }
    expected = {
        (p["policy_key"], p["agent_type"], p["tool_name"], p["action"].value): True
        for p in SEED_POLICIES
    }
    assert actual == expected


def test_seed_permissions_match_expected_matrix(db_session):
    seed(db_session)

    agent_names = {agent.id: agent.name for agent in db_session.query(Agent).all()}
    tool_names = {tool.id: tool.name for tool in db_session.query(Tool).all()}
    actual = {
        (agent_names[permission.agent_id], tool_names[permission.tool_id]): permission.permission
        for permission in db_session.query(AgentToolPermission).all()
    }
    expected = {
        (row["agent_name"], row["tool_name"]): row["permission"]
        for row in SEED_PERMISSIONS
    }

    assert len(SEED_PERMISSIONS) == 16
    assert actual == expected
