"""Add detailed candidate scoring fields.

Revision ID: a3c1f8e2b7d4
Revises: 49fde827afb1
Create Date: 2026-07-20
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "a3c1f8e2b7d4"
down_revision: Union[str, Sequence[str], None] = "49fde827afb1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "scored_candidates",
        sa.Column("semantic_similarity", sa.Float(), nullable=False, server_default="0"),
    )
    op.add_column(
        "scored_candidates",
        sa.Column("llm_rerank_score", sa.Float(), nullable=False, server_default="0"),
    )
    op.add_column(
        "scored_candidates",
        sa.Column(
            "matched_skills_json",
            sa.JSON(),
            nullable=False,
            server_default=sa.text("'[]'::json"),
        ),
    )
    op.add_column(
        "scored_candidates",
        sa.Column(
            "missing_skills_json",
            sa.JSON(),
            nullable=False,
            server_default=sa.text("'[]'::json"),
        ),
    )


def downgrade() -> None:
    op.drop_column("scored_candidates", "missing_skills_json")
    op.drop_column("scored_candidates", "matched_skills_json")
    op.drop_column("scored_candidates", "llm_rerank_score")
    op.drop_column("scored_candidates", "semantic_similarity")
