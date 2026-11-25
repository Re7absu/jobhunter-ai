"""Remove the auto-send option: automation never sends emails.

Revision ID: 0002_remove_auto_send
Revises: 9217ec6d0a14
"""

import sqlalchemy as sa
from alembic import op

revision = "0002_remove_auto_send"
down_revision = "9217ec6d0a14"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("automation_settings") as batch:
        batch.drop_column("auto_send_approved")


def downgrade() -> None:
    with op.batch_alter_table("automation_settings") as batch:
        batch.add_column(sa.Column("auto_send_approved", sa.Boolean(), nullable=False, server_default=sa.false()))
