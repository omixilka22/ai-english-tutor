"""Durable Recall sessions and deduplicated, content-free webhook inbox."""
from alembic import op
import sqlalchemy as sa
revision='b0743cf65e89'
down_revision='a9632be54d78'
branch_labels=None
depends_on=None


def upgrade():
    op.create_table('recall_sessions',
        sa.Column('id',sa.String(36),primary_key=True),
        sa.Column('lesson_id',sa.Integer(),sa.ForeignKey('lessons.id'),unique=True,nullable=False),
        sa.Column('bot_id',sa.String(36),unique=True),
        sa.Column('recording_id',sa.String(36),unique=True),
        sa.Column('transcript_id',sa.String(36),unique=True),
        sa.Column('meeting_url',sa.String(255)),
        sa.Column('state',sa.String(32),nullable=False),
        sa.Column('error',sa.String(64)),
        sa.Column('attempts',sa.Integer(),nullable=False,server_default='0'),
        sa.Column('next_attempt_at',sa.DateTime(timezone=True)),
        sa.Column('stop_at',sa.DateTime(timezone=True),nullable=False),
        sa.Column('leave_requested',sa.Boolean(),nullable=False,server_default='false'),
        sa.Column('leave_sent',sa.Boolean(),nullable=False,server_default='false'),
        sa.Column('created_at',sa.DateTime(timezone=True),nullable=False),
        sa.Column('expires_at',sa.DateTime(timezone=True),nullable=False),
        sa.Column('cleanup_state',sa.String(20),nullable=False,server_default='none'),
        sa.Column('cleanup_after',sa.DateTime(timezone=True)),
        sa.Column('notice_sent',sa.Boolean(),nullable=False,server_default='false'))
    op.create_table('recall_events',
        sa.Column('id',sa.String(255),primary_key=True),
        sa.Column('event',sa.String(64),nullable=False),
        sa.Column('bot_id',sa.String(36),nullable=False),
        sa.Column('session_id',sa.String(36)),
        sa.Column('recording_id',sa.String(36)),
        sa.Column('transcript_id',sa.String(36)),
        sa.Column('done',sa.Boolean(),nullable=False,server_default='false'),
        sa.Column('created_at',sa.DateTime(timezone=True),nullable=False))


def downgrade():
    op.drop_table('recall_events')
    op.drop_table('recall_sessions')
