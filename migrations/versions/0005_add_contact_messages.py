"""add contact messages

Revision ID: 0005
Revises: 0004
Create Date: 2026-11-14 12:00:00

"""
from alembic import op
import sqlalchemy as sa


revision = '0005'
down_revision = '0004'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('contact_messages',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('first_name', sa.String(length=60), nullable=False),
    sa.Column('last_name', sa.String(length=60), nullable=False),
    sa.Column('email', sa.String(length=190), nullable=False),
    sa.Column('subject', sa.String(length=160), nullable=False),
    sa.Column('body', sa.Text(), nullable=False),
    sa.Column('consent', sa.Boolean(), nullable=False),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.Column('handled_at', sa.DateTime(), nullable=True),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('contact_messages', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_contact_messages_created_at'), ['created_at'], unique=False)


def downgrade():
    with op.batch_alter_table('contact_messages', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_contact_messages_created_at'))
    op.drop_table('contact_messages')
