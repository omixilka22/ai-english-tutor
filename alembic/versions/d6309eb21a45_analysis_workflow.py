"""Durable transcript analysis, review and approved delivery."""
from alembic import op
import sqlalchemy as sa
revision='d6309eb21a45'
down_revision='c52a8f901e76'
branch_labels=None
depends_on=None


def upgrade():
    for column in [
        sa.Column('workflow_state',sa.String(24),nullable=False,server_default='legacy'),
        sa.Column('revision',sa.Integer(),nullable=False,server_default='1'),
        sa.Column('last_error',sa.String(64),nullable=True),
        sa.Column('attempts',sa.Integer(),nullable=False,server_default='0'),
        sa.Column('next_attempt_at',sa.DateTime(timezone=True),nullable=True),
        sa.Column('telegram_message_id',sa.BigInteger(),nullable=True),
        sa.Column('review_notified',sa.Boolean(),nullable=False,server_default=sa.false()),
    ]:
        op.add_column('lesson_analyses',column)
    op.create_index('ix_analysis_workflow','lesson_analyses',['workflow_state','next_attempt_at'])


def downgrade():
    op.drop_index('ix_analysis_workflow',table_name='lesson_analyses')
    for name in ['review_notified','telegram_message_id','next_attempt_at','attempts','last_error','revision','workflow_state']:
        op.drop_column('lesson_analyses',name)
