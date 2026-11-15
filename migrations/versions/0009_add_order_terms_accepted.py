"""add order terms accepted

Revision ID: 0009
Revises: 0008
Create Date: 2026-11-15 06:40:00

"""
from alembic import op
import sqlalchemy as sa


revision = '0009'
down_revision = '0008'
branch_labels = None
depends_on = None


def upgrade():
    # When the buyer agreed to the Terms of Sale, Privacy Policy and Refund Policy at checkout. Nullable: orders placed
    # before v1.4 have no record of it, and nothing is backfilled.
    with op.batch_alter_table('orders', schema=None) as batch_op:
        batch_op.add_column(sa.Column('terms_accepted_at', sa.DateTime(), nullable=True))


def downgrade():
    with op.batch_alter_table('orders', schema=None) as batch_op:
        batch_op.drop_column('terms_accepted_at')
