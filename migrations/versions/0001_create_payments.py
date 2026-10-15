"""create payments table

Revision ID: 0001_create_payments
Revises:
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "0001_create_payments"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "payments",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("external_id", sa.String(length=100), nullable=False),
        sa.Column("execute_on", sa.Date(), nullable=False),
        sa.Column("amount", sa.Numeric(precision=18, scale=2), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column(
            "payload",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="pending"),
        sa.Column("factory_request_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("factory_payment_id", sa.String(length=100), nullable=True),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("queued_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("processing_started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("next_attempt_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("external_id", name="uq_payments_external_id"),
        sa.UniqueConstraint("factory_request_id", name="uq_payments_factory_request_id"),
    )
    op.create_index(
        "ix_payments_execute_on_status", "payments", ["execute_on", "status"]
    )
    op.create_index(
        "ix_payments_status_next_attempt", "payments", ["status", "next_attempt_at"]
    )


def downgrade() -> None:
    op.drop_index("ix_payments_status_next_attempt", table_name="payments")
    op.drop_index("ix_payments_execute_on_status", table_name="payments")
    op.drop_table("payments")

