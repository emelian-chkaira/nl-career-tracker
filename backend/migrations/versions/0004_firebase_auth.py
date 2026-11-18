"""firebase identity link

Revision ID: 0004
Revises: 0003
"""
from alembic import op
import sqlalchemy as sa

revision = '0004'
down_revision = '0003'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('users', sa.Column('firebase_uid', sa.String(length=128), nullable=True))
    op.add_column('users', sa.Column('firebase_refresh', sa.String(length=2048), nullable=True))
    op.create_index(op.f('ix_users_firebase_uid'), 'users', ['firebase_uid'], unique=True)


def downgrade() -> None:
    op.drop_index(op.f('ix_users_firebase_uid'), table_name='users')
    op.drop_column('users', 'firebase_refresh')
    op.drop_column('users', 'firebase_uid')
