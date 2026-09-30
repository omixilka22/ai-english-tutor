"""Lesson calendar snapshots, recurrence identity and cancellation.

Revision ID: 7c1a9b0d5e22
Revises: 13fd426b79da
"""
from alembic import op
import sqlalchemy as sa

revision = '7c1a9b0d5e22'
down_revision = '13fd426b79da'
branch_labels = None
depends_on = None


def upgrade():
    op.execute("ALTER TYPE lessonstatus ADD VALUE IF NOT EXISTS 'CANCELLED'")
    op.add_column('lessons',sa.Column('occurrence_week',sa.Date(),nullable=True))
    op.add_column('lessons',sa.Column('duration_minutes',sa.Integer(),nullable=False,server_default='60'))
    op.add_column('lessons',sa.Column('timezone',sa.String(64),nullable=False,server_default='Europe/Kyiv'))
    op.add_column('lessons',sa.Column('is_exception',sa.Boolean(),nullable=False,server_default=sa.false()))
    op.execute('''UPDATE lessons l SET duration_minutes=s.duration_minutes, timezone=s.timezone,
        occurrence_week=date_trunc('week', l.scheduled_at AT TIME ZONE s.timezone)::date
        FROM weekly_schedules s WHERE l.schedule_id=s.id''')
    # Keep pre-existing duplicates intact as explicit exceptions, with no recurrence slot.
    op.execute('''WITH ranked AS (
        SELECT id,row_number() OVER (PARTITION BY schedule_id,occurrence_week ORDER BY id) n
        FROM lessons WHERE schedule_id IS NOT NULL
    ) UPDATE lessons SET occurrence_week=NULL,is_exception=true
      WHERE id IN (SELECT id FROM ranked WHERE n>1)''')
    op.create_unique_constraint('uq_lesson_schedule_week','lessons',['schedule_id','occurrence_week'])
    op.create_index('ix_lessons_student_time','lessons',['student_id','scheduled_at'])


def downgrade():
    # Do not silently erase cancellations or manual exceptions when rolling back.
    op.execute("""DO $$ BEGIN
        IF EXISTS (SELECT 1 FROM lessons WHERE status::text='CANCELLED' OR is_exception) THEN
            RAISE EXCEPTION 'Cannot downgrade while cancelled or exceptional lessons exist';
        END IF;
    END $$""")
    op.drop_index('ix_lessons_student_time',table_name='lessons')
    op.drop_constraint('uq_lesson_schedule_week','lessons',type_='unique')
    for name in ['is_exception','timezone','duration_minutes','occurrence_week']:
        op.drop_column('lessons',name)
    # PostgreSQL enum labels cannot be removed in place; the unused label remains.
