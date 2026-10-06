"""login attempts (rate limiting)

Revision ID: 7e1a0b2c0d00
Revises: c799fea24979
Create Date: 2026-09-16 16:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '7e1a0b2c0d00'
down_revision: Union[str, Sequence[str], None] = 'c799fea24979'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'login_attempts',
        sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column('email', sa.Text(), nullable=False),
        sa.Column('ip_address', sa.Text(), nullable=True),
        sa.Column('success', sa.Boolean(), nullable=False),
        sa.Column(
            'created_at',
            sa.DateTime(timezone=True),
            server_default=sa.text('now()'),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(
        op.f('ix_login_attempts_created_at'), 'login_attempts', ['created_at'], unique=False
    )
    op.create_index(
        op.f('ix_login_attempts_email'), 'login_attempts', ['email'], unique=False
    )
    op.create_index(
        op.f('ix_login_attempts_ip_address'), 'login_attempts', ['ip_address'], unique=False
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f('ix_login_attempts_ip_address'), table_name='login_attempts')
    op.drop_index(op.f('ix_login_attempts_email'), table_name='login_attempts')
    op.drop_index(op.f('ix_login_attempts_created_at'), table_name='login_attempts')
    op.drop_table('login_attempts')