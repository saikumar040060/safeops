from sqlalchemy.orm import Session

from app.core.database import SessionLocal
from app.models import Agent, Tool
from app.models.enums import AgentStatus, RiskLevel

SEED_AGENTS = [
    {
        "name": "support-agent",
        "type": "support",
        "description": "Investigates and resolves customer support issues.",
        "status": AgentStatus.ACTIVE,
        "risk_level": RiskLevel.MEDIUM,
    },
    {
        "name": "devops-agent",
        "type": "devops",
        "description": "Diagnoses and remediates production incidents.",
        "status": AgentStatus.ACTIVE,
        "risk_level": RiskLevel.HIGH,
    },
]

SEED_TOOLS = [
    {
        "name": "read_customer",
        "description": "Read a customer's profile and account details.",
        "risk_category": RiskLevel.LOW,
    },
    {
        "name": "get_payments",
        "description": "List a customer's payment history.",
        "risk_category": RiskLevel.LOW,
    },
    {
        "name": "refund_payment",
        "description": "Issue a refund for a payment.",
        "risk_category": RiskLevel.HIGH,
    },
    {
        "name": "read_logs",
        "description": "Read service logs.",
        "risk_category": RiskLevel.LOW,
    },
    {
        "name": "deploy_staging",
        "description": "Deploy a build to the staging environment.",
        "risk_category": RiskLevel.MEDIUM,
    },
    {
        "name": "deploy_production",
        "description": "Deploy a build to the production environment.",
        "risk_category": RiskLevel.CRITICAL,
    },
]


def seed(db: Session) -> None:
    for data in SEED_AGENTS:
        existing = db.query(Agent).filter_by(name=data["name"]).one_or_none()
        if existing is None:
            db.add(Agent(**data))

    for data in SEED_TOOLS:
        existing = db.query(Tool).filter_by(name=data["name"]).one_or_none()
        if existing is None:
            db.add(Tool(**data))

    db.commit()


def main() -> None:
    db = SessionLocal()
    try:
        seed(db)
    finally:
        db.close()


if __name__ == "__main__":
    main()
