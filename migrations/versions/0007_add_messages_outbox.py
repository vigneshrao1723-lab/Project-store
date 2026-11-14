"""add messages outbox and contact opt-outs

Revision ID: 0007
Revises: 0006
Create Date: 2026-11-14 12:00:02

"""
from alembic import op
import sqlalchemy as sa


revision = '0007'
down_revision = '0006'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('messages',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('order_id', sa.Integer(), nullable=False),
    sa.Column('kind', sa.String(length=24), nullable=False),
    sa.Column('channel', sa.String(length=16), nullable=False),
    sa.Column('to_value', sa.String(length=190), nullable=False),
    sa.Column('to_hash', sa.String(length=64), nullable=False),
    sa.Column('subject', sa.String(length=200), nullable=False),
    sa.Column('body_text', sa.Text(), nullable=False),
    sa.Column('body_html', sa.Text(), nullable=False),
    sa.Column('status', sa.String(length=16), nullable=False),
    sa.Column('attempts', sa.Integer(), nullable=False),
    sa.Column('last_error', sa.String(length=200), nullable=False),
    sa.Column('next_attempt_at', sa.DateTime(), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.Column('sent_at', sa.DateTime(), nullable=True),
    sa.ForeignKeyConstraint(['order_id'], ['orders.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('order_id', 'kind', 'channel', name='uq_messages_order_kind_channel')
    )
    with op.batch_alter_table('messages', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_messages_created_at'), ['created_at'], unique=False)
        batch_op.create_index(batch_op.f('ix_messages_order_id'), ['order_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_messages_status'), ['status'], unique=False)
        batch_op.create_index(batch_op.f('ix_messages_to_hash'), ['to_hash'], unique=False)
    op.create_table('contact_optouts',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('value_hash', sa.String(length=64), nullable=False),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('value_hash')
    )


def downgrade():
    op.drop_table('contact_optouts')
    with op.batch_alter_table('messages', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_messages_to_hash'))
        batch_op.drop_index(batch_op.f('ix_messages_status'))
        batch_op.drop_index(batch_op.f('ix_messages_order_id'))
        batch_op.drop_index(batch_op.f('ix_messages_created_at'))
    op.drop_table('messages')
