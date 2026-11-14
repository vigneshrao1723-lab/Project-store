"""add product setup guide

Revision ID: 0008
Revises: 0007
Create Date: 2026-11-14 12:00:03

"""
from alembic import op
import sqlalchemy as sa


revision = '0008'
down_revision = '0007'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('products', schema=None) as batch_op:
        batch_op.add_column(sa.Column('setup_guide', sa.Text(), nullable=True))      # MySQL allows no literal default on TEXT
        batch_op.add_column(sa.Column('guide_edited', sa.Boolean(), server_default=sa.false(), nullable=False))


def downgrade():
    with op.batch_alter_table('products', schema=None) as batch_op:
        batch_op.drop_column('guide_edited')
        batch_op.drop_column('setup_guide')
