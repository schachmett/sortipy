"""reconciliation schema fields

Revision ID: b7f9c7f4d2b1
Revises: 822b044566e8
Create Date: 2026-03-07 12:00:00.000000

"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

from sortipy.adapters.sqlalchemy import mappings as sa_mappings
from sortipy.domain.model import (
    ArtistKind,
    ReleasePackaging,
    ReleaseStatus,
)

# revision identifiers, used by Alembic.
revision: str = "b7f9c7f4d2b1"
down_revision: tuple[str, ...] | str | None = "822b044566e8"
branch_labels: tuple[str, ...] | str | None = None
depends_on: tuple[str, ...] | str | None = None


def upgrade() -> None:
    """Upgrade schema."""

    with op.batch_alter_table("artist", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column("kind", sa.Enum(ArtistKind, native_enum=False), nullable=True)
        )
        batch_op.add_column(sa.Column("life_span", sa_mappings.LifeSpanType(), nullable=True))
        batch_op.add_column(sa.Column("areas", sa_mappings.AreaListType(), nullable=True))
        batch_op.add_column(sa.Column("aliases", sa_mappings.StringListType(), nullable=True))

    with op.batch_alter_table("release_set", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column(
                "secondary_types",
                sa_mappings.ReleaseSetSecondaryTypesType(),
                nullable=True,
            )
        )
        batch_op.add_column(sa.Column("aliases", sa_mappings.StringListType(), nullable=True))

    with op.batch_alter_table("release", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column("status", sa.Enum(ReleaseStatus, native_enum=False), nullable=True)
        )
        batch_op.add_column(
            sa.Column("packaging", sa.Enum(ReleasePackaging, native_enum=False), nullable=True)
        )

    with op.batch_alter_table("recording", schema=None) as batch_op:
        batch_op.add_column(sa.Column("aliases", sa_mappings.StringListType(), nullable=True))

    with op.batch_alter_table("recording_contribution", schema=None) as batch_op:
        batch_op.add_column(sa.Column("join_phrase", sa.String(), nullable=True))
        batch_op.drop_column("instrument")


def downgrade() -> None:
    """Downgrade schema."""

    with op.batch_alter_table("recording_contribution", schema=None) as batch_op:
        batch_op.add_column(sa.Column("instrument", sa.String(), nullable=True))
        batch_op.drop_column("join_phrase")

    with op.batch_alter_table("recording", schema=None) as batch_op:
        batch_op.drop_column("aliases")

    with op.batch_alter_table("release", schema=None) as batch_op:
        batch_op.drop_column("packaging")
        batch_op.drop_column("status")

    with op.batch_alter_table("release_set", schema=None) as batch_op:
        batch_op.drop_column("aliases")
        batch_op.drop_column("secondary_types")

    with op.batch_alter_table("artist", schema=None) as batch_op:
        batch_op.drop_column("aliases")
        batch_op.drop_column("areas")
        batch_op.drop_column("life_span")
        batch_op.drop_column("kind")
