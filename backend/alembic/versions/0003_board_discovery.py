"""Company board auto-discovery, SmartRecruiters, discovery method and multi-source tracking.

Revision ID: 0003_board_discovery
Revises: 0002_remove_auto_send
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0003_board_discovery"
down_revision = "0002_remove_auto_send"
branch_labels = None
depends_on = None

JSON = sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql")


def upgrade() -> None:
    with op.batch_alter_table("companies") as b:
        b.add_column(sa.Column("tracking_source", sa.String(10), nullable=True))
        b.add_column(sa.Column("board_detected_from", sa.String(500), nullable=True))
        b.add_column(sa.Column("last_scanned_at", sa.DateTime(), nullable=True))
        b.add_column(sa.Column("scan_error", sa.Text(), nullable=True))
        b.create_index("ix_companies_last_scanned_at", ["last_scanned_at"])
    op.execute("UPDATE companies SET tracking_source = 'manual' WHERE tracked = true")
    with op.batch_alter_table("jobs") as b:
        b.add_column(sa.Column("discovery_method", sa.String(30), nullable=False, server_default="search_api"))
        b.add_column(sa.Column("seen_sources", JSON, nullable=False, server_default="[]"))
        b.create_index("ix_jobs_discovery_method", ["discovery_method"])
    with op.batch_alter_table("automation_settings") as b:
        b.add_column(sa.Column("max_boards_per_run", sa.Integer(), nullable=False, server_default="15"))


def downgrade() -> None:
    with op.batch_alter_table("automation_settings") as b:
        b.drop_column("max_boards_per_run")
    with op.batch_alter_table("jobs") as b:
        b.drop_index("ix_jobs_discovery_method")
        b.drop_column("seen_sources")
        b.drop_column("discovery_method")
    with op.batch_alter_table("companies") as b:
        b.drop_index("ix_companies_last_scanned_at")
        b.drop_column("scan_error")
        b.drop_column("last_scanned_at")
        b.drop_column("board_detected_from")
        b.drop_column("tracking_source")
