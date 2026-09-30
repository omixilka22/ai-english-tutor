"""Durable lesson notifications and student preferences.

Revision ID: b410d59c7e32
Revises: 9d8e2a7f4b10
"""
from alembic import op
import sqlalchemy as sa
revision='b410d59c7e32'
down_revision='9d8e2a7f4b10'
branch_labels=None
depends_on=None


def upgrade():
    op.add_column('students',sa.Column('reminders_enabled',sa.Boolean(),nullable=False,server_default=sa.true()))
    op.add_column('lessons',sa.Column('notification_version',sa.Integer(),nullable=False,server_default='1'))
    op.add_column('lessons',sa.Column('notification_since',sa.DateTime(timezone=True),nullable=False,server_default=sa.func.now()))
    op.create_table('lesson_notifications',
        sa.Column('id',sa.Integer(),primary_key=True),
        sa.Column('lesson_id',sa.Integer(),sa.ForeignKey('lessons.id'),nullable=False),
        sa.Column('student_id',sa.Integer(),sa.ForeignKey('students.id'),nullable=False),
        sa.Column('revision',sa.Integer(),nullable=False),
        sa.Column('kind',sa.String(32),nullable=False),
        sa.Column('status',sa.String(16),nullable=False,server_default='pending'),
        sa.Column('due_at',sa.DateTime(timezone=True),nullable=False),
        sa.Column('expires_at',sa.DateTime(timezone=True),nullable=False),
        sa.Column('next_attempt_at',sa.DateTime(timezone=True),nullable=False),
        sa.Column('attempts',sa.Integer(),nullable=False,server_default='0'),
        sa.Column('sent_at',sa.DateTime(timezone=True),nullable=True),
        sa.Column('telegram_message_id',sa.BigInteger(),nullable=True),
        sa.Column('last_error',sa.String(128),nullable=True),
        sa.Column('created_at',sa.DateTime(timezone=True),nullable=False,server_default=sa.func.now()),
        sa.UniqueConstraint('lesson_id','revision','kind','student_id',name='uq_lesson_notification'))
    op.create_index('ix_notifications_pending','lesson_notifications',['status','next_attempt_at'])


def downgrade():
    op.drop_index('ix_notifications_pending',table_name='lesson_notifications')
    op.drop_table('lesson_notifications')
    op.drop_column('lessons','notification_since')
    op.drop_column('lessons','notification_version')
    op.drop_column('students','reminders_enabled')
