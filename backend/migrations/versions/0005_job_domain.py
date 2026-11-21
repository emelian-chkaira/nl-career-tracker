"""job domain (mobile, backend, ...) for storage filters and search

Revision ID: 0005
Revises: 0004
"""
from alembic import op
import sqlalchemy as sa

revision = '0005'
down_revision = '0004'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('jobs', sa.Column('domain', sa.String(length=16), nullable=True))
    op.create_index(op.f('ix_jobs_domain'), 'jobs', ['domain'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_jobs_domain'), table_name='jobs')
    op.drop_column('jobs', 'domain')
