"""agent harness foundations (runs, events, profiles, feedback, settings)

Revision ID: e4f1c2a9b7d3
Revises: 9497d72aa2e8
Create Date: 2026-10-29 18:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = 'e4f1c2a9b7d3'
down_revision: Union[str, Sequence[str], None] = '9497d72aa2e8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table('agent_profiles',
    sa.Column('id', sa.Uuid(), server_default=sa.text('gen_random_uuid()'), nullable=False),
    sa.Column('mode', sa.Text(), nullable=False),
    sa.Column('version', sa.Integer(), nullable=False),
    sa.Column('is_active', sa.Boolean(), server_default=sa.text('false'), nullable=False),
    sa.Column('system_prompt', sa.Text(), nullable=False),
    sa.Column('config', postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=False),
    sa.Column('created_by', sa.Uuid(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['created_by'], ['users.id'], ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('mode', 'version', name='uq_agent_profiles_mode_version')
    )
    op.create_index('uq_agent_profiles_active_mode', 'agent_profiles', ['mode'], unique=True, postgresql_where=sa.text('is_active'))

    op.create_table('agent_runs',
    sa.Column('id', sa.Uuid(), server_default=sa.text('gen_random_uuid()'), nullable=False),
    sa.Column('thread_id', sa.Uuid(), nullable=False),
    sa.Column('user_id', sa.Uuid(), nullable=False),
    sa.Column('user_message_id', sa.Uuid(), nullable=True),
    sa.Column('assistant_message_id', sa.Uuid(), nullable=False),
    sa.Column('kind', sa.Text(), nullable=False),
    sa.Column('mode', sa.Text(), nullable=False),
    sa.Column('profile_version_id', sa.Uuid(), nullable=True),
    sa.Column('catalog_slug', sa.Text(), nullable=True),
    sa.Column('provider_model_id', sa.Uuid(), nullable=True),
    sa.Column('model_label', sa.Text(), nullable=True),
    sa.Column('status', sa.Text(), server_default=sa.text("'queued'"), nullable=False),
    sa.Column('error_code', sa.Text(), nullable=True),
    sa.Column('error_message', sa.Text(), nullable=True),
    sa.Column('input_tokens', sa.Integer(), server_default=sa.text('0'), nullable=False),
    sa.Column('output_tokens', sa.Integer(), server_default=sa.text('0'), nullable=False),
    sa.Column('cost_estimate', sa.Numeric(precision=12, scale=6), nullable=True),
    sa.Column('ttft_ms', sa.Integer(), nullable=True),
    sa.Column('hallucinated_citations', sa.Integer(), server_default=sa.text('0'), nullable=False),
    sa.Column('trace_url', sa.Text(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('started_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('finished_at', sa.DateTime(timezone=True), nullable=True),
    sa.ForeignKeyConstraint(['assistant_message_id'], ['messages.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['profile_version_id'], ['agent_profiles.id'], ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['provider_model_id'], ['provider_models.id'], ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['thread_id'], ['threads.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['user_message_id'], ['messages.id'], ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_agent_runs_thread_created', 'agent_runs', ['thread_id', 'created_at'], unique=False)

    op.create_table('agent_run_events',
    sa.Column('id', sa.BigInteger(), sa.Identity(), nullable=False),
    sa.Column('run_id', sa.Uuid(), nullable=False),
    sa.Column('seq', sa.Integer(), nullable=False),
    sa.Column('type', sa.Text(), nullable=False),
    sa.Column('payload', postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['run_id'], ['agent_runs.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('run_id', 'seq', name='uq_agent_run_events_run_seq')
    )
    op.create_index(op.f('ix_agent_run_events_run_id'), 'agent_run_events', ['run_id'], unique=False)

    op.create_table('message_feedback',
    sa.Column('id', sa.Uuid(), server_default=sa.text('gen_random_uuid()'), nullable=False),
    sa.Column('message_id', sa.Uuid(), nullable=False),
    sa.Column('user_id', sa.Uuid(), nullable=False),
    sa.Column('value', sa.Text(), nullable=False),
    sa.Column('reason', sa.Text(), nullable=True),
    sa.Column('comment', sa.Text(), nullable=True),
    sa.Column('reviewed_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint("value IN ('good', 'bad')", name='ck_message_feedback_value'),
    sa.ForeignKeyConstraint(['message_id'], ['messages.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('message_id', 'user_id', name='uq_message_feedback_message_user')
    )
    op.create_index(op.f('ix_message_feedback_message_id'), 'message_feedback', ['message_id'], unique=False)
    op.create_index(op.f('ix_message_feedback_user_id'), 'message_feedback', ['user_id'], unique=False)

    op.create_table('app_settings',
    sa.Column('key', sa.Text(), nullable=False),
    sa.Column('value', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('updated_by', sa.Uuid(), nullable=True),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['updated_by'], ['users.id'], ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('key')
    )

    op.add_column('provider_models', sa.Column('supports_tools', sa.Boolean(), nullable=True))
    op.add_column('provider_models', sa.Column('context_window', sa.Integer(), nullable=True))
    op.add_column('provider_models', sa.Column('input_price_per_mtok', sa.Numeric(precision=12, scale=4), nullable=True))
    op.add_column('provider_models', sa.Column('output_price_per_mtok', sa.Numeric(precision=12, scale=4), nullable=True))

    op.add_column('threads', sa.Column('summary', sa.Text(), nullable=True))
    op.add_column('threads', sa.Column('summary_through_seq', sa.BigInteger(), nullable=True))
    op.add_column('threads', sa.Column('context_start_seq', sa.BigInteger(), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('threads', 'context_start_seq')
    op.drop_column('threads', 'summary_through_seq')
    op.drop_column('threads', 'summary')
    op.drop_column('provider_models', 'output_price_per_mtok')
    op.drop_column('provider_models', 'input_price_per_mtok')
    op.drop_column('provider_models', 'context_window')
    op.drop_column('provider_models', 'supports_tools')
    op.drop_table('app_settings')
    op.drop_index(op.f('ix_message_feedback_user_id'), table_name='message_feedback')
    op.drop_index(op.f('ix_message_feedback_message_id'), table_name='message_feedback')
    op.drop_table('message_feedback')
    op.drop_index(op.f('ix_agent_run_events_run_id'), table_name='agent_run_events')
    op.drop_table('agent_run_events')
    op.drop_index('ix_agent_runs_thread_created', table_name='agent_runs')
    op.drop_table('agent_runs')
    op.drop_index('uq_agent_profiles_active_mode', table_name='agent_profiles', postgresql_where=sa.text('is_active'))
    op.drop_table('agent_profiles')
