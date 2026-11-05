"""kb chunks with embeddings for RAG

Revision ID: d3a8f1c5e920
Revises: b7c3e9d1a2f4
Create Date: 2026-11-05 14:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = 'd3a8f1c5e920'
down_revision: Union[str, Sequence[str], None] = 'b7c3e9d1a2f4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table('kb_chunks',
    sa.Column('id', sa.Uuid(), server_default=sa.text('gen_random_uuid()'), nullable=False),
    sa.Column('document_id', sa.Uuid(), nullable=False),
    sa.Column('position', sa.Integer(), nullable=False),
    sa.Column('heading', sa.Text(), server_default=sa.text("''"), nullable=False),
    sa.Column('text', sa.Text(), nullable=False),
    sa.Column('embedding', postgresql.ARRAY(sa.Float()), nullable=False),
    sa.Column('model', sa.Text(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['document_id'], ['kb_documents.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_kb_chunks_document_id', 'kb_chunks', ['document_id'], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index('ix_kb_chunks_document_id', table_name='kb_chunks')
    op.drop_table('kb_chunks')
