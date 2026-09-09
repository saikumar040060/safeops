"""Milestone 10 section 7/21: lease-based stepping claim recovery.

Safety model under test (see agent_runtime.py module docstring for the
full argument): a claim older than LEASE_TTL is stale and safely
recoverable; a fresh claim cannot be stolen; concurrent recovery attempts
against the same stale lease produce exactly one winner; and recovery
never causes a duplicate tool-call side effect.
"""

import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta

from sqlalchemy.orm import Session

from app.models import Agent, Deployment, Execution
from app.services.agent_runtime import LEASE_TTL, AgentRuntime

runtime = AgentRuntime()


def _agent(db, name) -> Agent:
    return db.query(Agent).filter_by(name=name).one()


def _start_staging_deploy(db) -> uuid.UUID:
    agent = _agent(db, "devops-agent")
    start = runtime.start_execution(
        agent_id=agent.id,
        objective="Deploy checkout-service version 9.9.9 to staging",
        db=db,
    )
    return uuid.UUID(start.execution_id)


def test_fresh_claim_cannot_be_stolen(seeded_db):
    execution_id = _start_staging_deploy(seeded_db)
    execution = seeded_db.get(Execution, execution_id)

    claim_id = AgentRuntime._claim_stepping(seeded_db, execution)
    assert claim_id is not None

    # A second claim attempt immediately after must fail -- the lease is
    # fresh, not stale.
    second = AgentRuntime._claim_stepping(seeded_db, execution)
    assert second is None

    AgentRuntime._release_stepping(seeded_db, execution_id, claim_id)


def test_stale_claim_is_recovered(seeded_db):
    execution_id = _start_staging_deploy(seeded_db)
    execution = seeded_db.get(Execution, execution_id)

    claim_id = AgentRuntime._claim_stepping(seeded_db, execution)
    assert claim_id is not None

    # Simulate the holder having crashed a while ago: back-date the claim
    # past the lease TTL directly in the DB.
    stale_time = datetime.now(UTC) - LEASE_TTL - timedelta(seconds=5)
    seeded_db.execute(
        Execution.__table__.update()
        .where(Execution.id == execution_id)
        .values(stepping_claimed_at=stale_time)
    )
    seeded_db.commit()
    seeded_db.refresh(execution)

    recovered_claim_id = AgentRuntime._claim_stepping(seeded_db, execution)
    assert recovered_claim_id is not None
    assert recovered_claim_id != claim_id


def test_zombie_holder_cannot_clear_a_recovered_claim(seeded_db):
    execution_id = _start_staging_deploy(seeded_db)
    execution = seeded_db.get(Execution, execution_id)

    original_claim_id = AgentRuntime._claim_stepping(seeded_db, execution)
    stale_time = datetime.now(UTC) - LEASE_TTL - timedelta(seconds=5)
    seeded_db.execute(
        Execution.__table__.update()
        .where(Execution.id == execution_id)
        .values(stepping_claimed_at=stale_time)
    )
    seeded_db.commit()
    seeded_db.refresh(execution)

    new_claim_id = AgentRuntime._claim_stepping(seeded_db, execution)
    assert new_claim_id is not None

    # The original (zombie) holder finally wakes up and tries to release
    # its own, now-stolen claim id -- this must be a no-op.
    AgentRuntime._release_stepping(seeded_db, execution_id, original_claim_id)

    seeded_db.refresh(execution)
    assert execution.stepping is True
    assert execution.stepping_claim_id == new_claim_id


def test_concurrent_recovery_of_the_same_stale_lease_has_exactly_one_winner(db_engine, seeded_db):
    execution_id = _start_staging_deploy(seeded_db)
    execution = seeded_db.get(Execution, execution_id)
    AgentRuntime._claim_stepping(seeded_db, execution)

    stale_time = datetime.now(UTC) - LEASE_TTL - timedelta(seconds=5)
    seeded_db.execute(
        Execution.__table__.update()
        .where(Execution.id == execution_id)
        .values(stepping_claimed_at=stale_time)
    )
    seeded_db.commit()

    from threading import Barrier

    barrier = Barrier(8)

    def attempt_recovery():
        with Session(db_engine) as session:
            exec_row = session.get(Execution, execution_id)
            barrier.wait(timeout=5)
            return AgentRuntime._claim_stepping(session, exec_row)

    with ThreadPoolExecutor(max_workers=8) as executor:
        results = list(executor.map(lambda _: attempt_recovery(), range(8)))

    winners = [r for r in results if r is not None]
    assert len(winners) == 1


def test_stale_lease_recovery_causes_no_duplicate_deploy(seeded_db):
    # Simulate a process that claimed the lease, executed the deploy tool
    # call (the side effect landed), then crashed before finalizing the
    # step -- the classic "crash mid-step" window. A subsequent step()
    # call after the lease goes stale must not create a second deployment.
    execution_id = _start_staging_deploy(seeded_db)
    r1 = runtime.step(execution_id, seeded_db)
    assert r1.status == "EXECUTED" and r1.tool_name == "get_deployment"

    execution = seeded_db.get(Execution, execution_id)
    claim_id = AgentRuntime._claim_stepping(seeded_db, execution)
    assert claim_id is not None

    # Manually run exactly what step() would have: plan -> tool call ->
    # gateway executes deploy_staging (the real side effect happens here)
    # -- but then "crash" by never calling _finalize/_release_stepping.
    result = AgentRuntime._advance(runtime, seeded_db, execution)
    assert result.status == "EXECUTED" and result.tool_name == "deploy_staging"

    deployments_after_first_run = (
        seeded_db.query(Deployment)
        .join(Deployment.service)
        .filter_by(name="checkout-service")
        .filter(Deployment.version == "9.9.9")
        .count()
    )
    assert deployments_after_first_run == 1

    # Do NOT release the lease -- simulate the crash. Back-date it past TTL.
    stale_time = datetime.now(UTC) - LEASE_TTL - timedelta(seconds=5)
    seeded_db.execute(
        Execution.__table__.update()
        .where(Execution.id == execution_id)
        .values(stepping_claimed_at=stale_time)
    )
    seeded_db.commit()

    # A fresh caller recovers the lease and steps again. Since the planner
    # is deterministic and re-derives from history, and `_attempted()`
    # already sees a deploy_staging TOOL_CALL step, it should move on to
    # Complete rather than re-attempting the tool -- but even if it did
    # attempt it again, the deploy tool's idempotency key must prevent a
    # second row (see test_deploy_idempotency.py for that guarantee
    # directly). Here we assert the end-to-end outcome: still exactly one
    # deployment row for this version.
    r2 = runtime.step(execution_id, seeded_db)
    assert r2.status in {"COMPLETED", "EXECUTED"}

    deployments_after_recovery = (
        seeded_db.query(Deployment)
        .join(Deployment.service)
        .filter_by(name="checkout-service")
        .filter(Deployment.version == "9.9.9")
        .count()
    )
    assert deployments_after_recovery == 1
