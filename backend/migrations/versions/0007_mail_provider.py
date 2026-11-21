"""mail account provider (imap | gmail oauth)

Revision ID: 0007
Revises: 0006
"""
from alembic import op
import sqlalchemy as sa

revision = '0007'
down_revision = '0006'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('mail_accounts', sa.Column('provider', sa.String(10), nullable=False, server_default='imap'))


def downgrade() -> None:
    op.drop_column('mail_accounts', 'provider')
