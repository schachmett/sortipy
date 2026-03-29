"""external id redirects

Revision ID: e7f7ef2162a5
Revises: b7f9c7f4d2b1
Create Date: 2026-03-29 14:30:00.000000

"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

from sortipy.adapters.sqlalchemy import mappings as sa_mappings
from sortipy.domain.model import Provider

# revision identifiers, used by Alembic.
revision: str = "e7f7ef2162a5"
down_revision: tuple[str, ...] | str | None = "b7f9c7f4d2b1"
branch_labels: tuple[str, ...] | str | None = None
depends_on: tuple[str, ...] | str | None = None


def upgrade() -> None:
    """Upgrade schema."""

    op.create_table(
        "external_id_redirect",
        sa.Column("id", sa_mappings.UUIDColumnType, nullable=False),
        sa.Column("namespace", sa.String(), nullable=False),
        sa.Column("source_value", sa.String(), nullable=False),
        sa.Column("target_value", sa.String(), nullable=False),
        sa.Column("provider", sa.Enum(Provider, native_enum=False), nullable=True),
        sa.Column(
            "created_at",
            sa_mappings.UTCDateTime(),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_external_id_redirect")),
        sa.UniqueConstraint(
            "namespace",
            "source_value",
            name=op.f("uq_external_id_redirect_namespace"),
        ),
    )
    op.create_index(
        op.f("ix_external_id_redirect_namespace_source"),
        "external_id_redirect",
        ["namespace", "source_value"],
        unique=False,
    )


def downgrade() -> None:
    """Downgrade schema."""

    op.drop_index(
        op.f("ix_external_id_redirect_namespace_source"),
        table_name="external_id_redirect",
    )
    op.drop_table("external_id_redirect")
