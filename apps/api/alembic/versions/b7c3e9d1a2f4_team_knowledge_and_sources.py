"""team knowledge base, integration credentials and attachment text

Revision ID: b7c3e9d1a2f4
Revises: e4f1c2a9b7d3
Create Date: 2026-10-29 20:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = 'b7c3e9d1a2f4'
down_revision: Union[str, Sequence[str], None] = 'e4f1c2a9b7d3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# Igual que app/models/kb.py::KB_TSV_EXPRESSION: español e inglés en el mismo tsvector.
KB_TSV_EXPRESSION = (
    "setweight(to_tsvector('spanish', coalesce(title, '')), 'A') || "
    "setweight(to_tsvector('english', coalesce(title, '')), 'A') || "
    "to_tsvector('spanish', coalesce(text, '')) || "
    "to_tsvector('english', coalesce(text, ''))"
)


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table('kb_documents',
    sa.Column('id', sa.Uuid(), server_default=sa.text('gen_random_uuid()'), nullable=False),
    sa.Column('slug', sa.Text(), nullable=False),
    sa.Column('title', sa.Text(), nullable=False),
    sa.Column('path', sa.Text(), nullable=False),
    sa.Column('source_filename', sa.Text(), nullable=False),
    sa.Column('content_type', sa.Text(), nullable=False),
    sa.Column('text', sa.Text(), server_default=sa.text("''"), nullable=False),
    sa.Column('tsv', postgresql.TSVECTOR(), sa.Computed(KB_TSV_EXPRESSION, persisted=True), nullable=True),
    sa.Column('tags', postgresql.ARRAY(sa.Text()), server_default=sa.text("'{}'"), nullable=False),
    sa.Column('is_enabled', sa.Boolean(), server_default=sa.text('true'), nullable=False),
    sa.Column('size_bytes', sa.BigInteger(), nullable=False),
    sa.Column('created_by', sa.Uuid(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['created_by'], ['users.id'], ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('slug')
    )
    op.create_index('ix_kb_documents_tsv', 'kb_documents', ['tsv'], unique=False, postgresql_using='gin')

    op.create_table('integration_credentials',
    sa.Column('id', sa.Uuid(), server_default=sa.text('gen_random_uuid()'), nullable=False),
    sa.Column('kind', sa.Text(), nullable=False),
    sa.Column('secret_ciphertext', sa.LargeBinary(), nullable=False),
    sa.Column('last_four', sa.Text(), nullable=False),
    sa.Column('is_active', sa.Boolean(), server_default=sa.text('false'), nullable=False),
    sa.Column('created_by', sa.Uuid(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['created_by'], ['users.id'], ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index('uq_integration_credentials_active_kind', 'integration_credentials', ['kind'], unique=True, postgresql_where=sa.text('is_active'))

    op.add_column('storage_objects', sa.Column('extracted_text', sa.Text(), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('storage_objects', 'extracted_text')
    op.drop_index('uq_integration_credentials_active_kind', table_name='integration_credentials')
    op.drop_table('integration_credentials')
    op.drop_index('ix_kb_documents_tsv', table_name='kb_documents')
    op.drop_table('kb_documents')
