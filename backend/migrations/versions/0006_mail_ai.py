"""AI settings, connected mailboxes and extracted job e-mails

Revision ID: 0006
Revises: 0005
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = '0006'
down_revision = '0005'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table('user_ai_settings',
        sa.Column('user_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('users.id', ondelete='CASCADE'), primary_key=True),
        sa.Column('provider', sa.String(30), nullable=False, server_default='rules'), sa.Column('model', sa.String(120)), sa.Column('base_url', sa.String(300)),
        sa.Column('api_key_enc', sa.Text()), sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now()))
    op.create_table('mail_accounts',
        sa.Column('id', sa.Integer(), primary_key=True), sa.Column('user_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
        sa.Column('label', sa.String(80), nullable=False), sa.Column('host', sa.String(200), nullable=False), sa.Column('port', sa.Integer(), nullable=False, server_default='993'),
        sa.Column('username', sa.String(200), nullable=False), sa.Column('secret_enc', sa.Text()), sa.Column('folder', sa.String(100), nullable=False, server_default='INBOX'),
        sa.Column('days_back', sa.Integer(), nullable=False, server_default='60'), sa.Column('last_sync_at', sa.DateTime(timezone=True)), sa.Column('last_error', sa.Text()),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()))
    op.create_index('ix_mail_accounts_user_id', 'mail_accounts', ['user_id'])
    op.create_table('mail_events',
        sa.Column('id', sa.Integer(), primary_key=True), sa.Column('user_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
        sa.Column('account_id', sa.Integer(), sa.ForeignKey('mail_accounts.id', ondelete='SET NULL')), sa.Column('message_id', sa.String(300), nullable=False),
        sa.Column('sender', sa.String(300)), sa.Column('subject', sa.String(400)), sa.Column('received_at', sa.DateTime(timezone=True)),
        sa.Column('category', sa.String(24), nullable=False), sa.Column('company', sa.String(200)), sa.Column('role', sa.String(250)), sa.Column('location', sa.String(200)),
        sa.Column('event_date', sa.String(80)), sa.Column('summary', sa.String(400)), sa.Column('confidence', sa.Float(), nullable=False, server_default='0.5'),
        sa.Column('classifier', sa.String(60), nullable=False, server_default='rules'), sa.Column('status', sa.String(12), nullable=False, server_default='new'),
        sa.Column('company_id', sa.Integer(), sa.ForeignKey('companies.id', ondelete='SET NULL')), sa.Column('job_id', sa.Integer(), sa.ForeignKey('jobs.id', ondelete='SET NULL')),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()), sa.UniqueConstraint('user_id', 'message_id', name='uq_mail_user_msg'))
    op.create_index('ix_mail_events_user_id', 'mail_events', ['user_id']); op.create_index('ix_mail_events_category', 'mail_events', ['category']); op.create_index('ix_mail_events_status', 'mail_events', ['status'])


def downgrade() -> None:
    op.drop_table('mail_events'); op.drop_table('mail_accounts'); op.drop_table('user_ai_settings')
