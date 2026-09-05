from app.core.seed import SEED_AGENTS, SEED_TOOLS, seed
from app.models import Agent, Tool


def test_seed_creates_expected_agents_and_tools(db_session):
    seed(db_session)

    assert db_session.query(Agent).count() == len(SEED_AGENTS)
    assert db_session.query(Tool).count() == len(SEED_TOOLS)

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
