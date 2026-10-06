"""threads and messages (conversation persistence)

Revision ID: 9f6e5d4c3b2a
Revises: 7e1a0b2c0d00
Create Date: 2026-09-16 18:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '9f6e5d4c3b2a'
down_revision: Union[str, Sequence[str], None] = '7e1a0b2c0d00'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'threads',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('owner_id', sa.Uuid(), nullable=False),
        sa.Column('client_id', sa.Text(), nullable=False),
        sa.Column('title', sa.Text(), nullable=True),
        sa.Column('mode', sa.Text(), server_default=sa.text("'learn'"), nullable=False),
        sa.Column(
            'created_at',
            sa.DateTime(timezone=True),
            server_default=sa.text('now()'),
            nullable=False,
        ),
        sa.Column(
            'updated_at',
            sa.DateTime(timezone=True),
            server_default=sa.text('now()'),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(['owner_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('owner_id', 'client_id', name='uq_threads_owner_client'),
    )
    op.create_index(op.f('ix_threads_owner_id'), 'threads', ['owner_id'], unique=False)
    op.create_table(
        'messages',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('thread_id', sa.Uuid(), nullable=False),
        sa.Column('client_id', sa.Text(), nullable=False),
        sa.Column('role', sa.Text(), nullable=False),
        sa.Column('text', sa.Text(), nullable=False),
        sa.Column('status', sa.Text(), server_default=sa.text("'complete'"), nullable=False),
        sa.Column('citations', sa.JSON(), nullable=True),
        sa.Column('attachment_ids', sa.JSON(), nullable=True),
        sa.Column('seq', sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column(
            'created_at',
            sa.DateTime(timezone=True),
            server_default=sa.text('now()'),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(['thread_id'], ['threads.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('thread_id', 'client_id', name='uq_messages_thread_client'),
    )
    op.create_index(op.f('ix_messages_thread_id'), 'messages', ['thread_id'], unique=False)
    op.create_index('ix_messages_thread_seq', 'messages', ['thread_id', 'seq'], unique=False)
    op.create_index(op.f('ix_messages_seq'), 'messages', ['seq'], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f('ix_messages_seq'), table_name='messages')
    op.drop_index('ix_messages_thread_seq', table_name='messages')
    op.drop_index(op.f('ix_messages_thread_id'), table_name='messages')
    op.drop_table('messages')
    op.drop_index(op.f('ix_threads_owner_id'), table_name='threads')
    op.drop_table('threads')