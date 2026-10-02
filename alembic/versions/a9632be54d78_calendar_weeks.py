"""Replace indefinite schedules with explicitly published calendar weeks.

Retirement is soft and audited; manual exceptions and materials are preserved.
"""
from alembic import op
import sqlalchemy as sa
revision = 'a9632be54d78'
down_revision = 'f8521ad43c67'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('weekly_schedules', sa.Column('week_start', sa.Date(), nullable=True))
    op.execute("UPDATE weekly_schedules SET week_start = date_trunc('week', CURRENT_TIMESTAMP AT TIME ZONE 'Europe/Kyiv')::date")
    op.alter_column('weekly_schedules', 'week_start', nullable=False)
    op.create_table('week_renewals',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('teacher_id', sa.Integer(), sa.ForeignKey('teachers.id'), nullable=False),
        sa.Column('week_start', sa.Date(), nullable=False),
        sa.Column('decision', sa.String(16), nullable=False, server_default='pending'),
        sa.Column('message_id', sa.BigInteger(), nullable=True),
        sa.UniqueConstraint('teacher_id', 'week_start', name='uq_teacher_week_renewal'))
    op.execute("INSERT INTO week_renewals (teacher_id, week_start, decision) SELECT DISTINCT teacher_id, week_start, 'new' FROM weekly_schedules")
    op.create_table('calendar_week_retired_lessons',
        sa.Column('lesson_id', sa.Integer(), sa.ForeignKey('lessons.id'), primary_key=True))
    op.execute("""
        INSERT INTO calendar_week_retired_lessons (lesson_id)
        SELECT l.id FROM lessons l
        WHERE l.schedule_id IS NOT NULL AND l.is_deleted = false AND l.is_exception = false
          AND l.status = 'SCHEDULED' AND l.conducted_at IS NULL
          AND l.scheduled_at >= ((date_trunc('week', CURRENT_TIMESTAMP AT TIME ZONE 'Europe/Kyiv')
                                  + interval '7 days') AT TIME ZONE 'Europe/Kyiv')
          AND NOT EXISTS (SELECT 1 FROM transcripts t WHERE t.lesson_id = l.id)
          AND NOT EXISTS (SELECT 1 FROM lesson_analyses a WHERE a.lesson_id = l.id)
    """)
    op.execute('UPDATE lessons SET is_deleted = true WHERE id IN (SELECT lesson_id FROM calendar_week_retired_lessons)')


def downgrade():
    # Restore only untouched rows retired by this migration, not later user deletions.
    op.execute("""UPDATE lessons SET is_deleted = false
        WHERE id IN (SELECT lesson_id FROM calendar_week_retired_lessons)
          AND is_exception = false AND status = 'SCHEDULED' AND conducted_at IS NULL""")
    op.drop_table('calendar_week_retired_lessons')
    op.drop_table('week_renewals')
    op.drop_column('weekly_schedules', 'week_start')
