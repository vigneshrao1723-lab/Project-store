"""add order contact choice

Revision ID: 0006
Revises: 0005
Create Date: 2026-11-14 12:00:01

"""
from alembic import op
import sqlalchemy as sa


revision = '0006'
down_revision = '0005'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('orders', schema=None) as batch_op:
        batch_op.add_column(sa.Column('contact_channel', sa.String(length=16), server_default='', nullable=False))
        batch_op.add_column(sa.Column('contact_value', sa.String(length=190), server_default='', nullable=False))
        batch_op.add_column(sa.Column('contact_consent_at', sa.DateTime(), nullable=True))


def downgrade():
    with op.batch_alter_table('orders', schema=None) as batch_op:
        batch_op.drop_column('contact_consent_at')
        batch_op.drop_column('contact_value')
        batch_op.drop_column('contact_channel')
