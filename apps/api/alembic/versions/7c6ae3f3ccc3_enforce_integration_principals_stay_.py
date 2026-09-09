"""enforce integration principals stay role viewer

Revision ID: 7c6ae3f3ccc3
Revises: 5e1b934b398f
Create Date: 2026-09-09 00:57:37.594433

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '7c6ae3f3ccc3'
down_revision: Union[str, Sequence[str], None] = '5e1b934b398f'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema.

    Milestone 11 security review finding: `Operator`'s docstring claimed
    an INTEGRATION-principal row always keeps `role=VIEWER` as defense in
    depth, but nothing actually enforced it -- only the seed script
    happened to always create rows that way. Adds the real constraint so
    a future INTEGRATION row can never be created (by any future code
    path, or a manual insert) with an elevated role.
    """
    op.create_check_constraint(
        "ck_operators_integration_role_viewer",
        "operators",
        "principal_type != 'INTEGRATION' OR role = 'VIEWER'",
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_constraint("ck_operators_integration_role_viewer", "operators", type_="check")
