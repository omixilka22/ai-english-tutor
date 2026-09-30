"""Reusable Meet links per student."""
from alembic import op
import sqlalchemy as sa
revision='c52a8f901e76'
down_revision='b410d59c7e32'
branch_labels=None
depends_on=None


def upgrade():
    op.add_column('students',sa.Column('meeting_url',sa.String(255),nullable=True))
    op.add_column('students',sa.Column('meeting_teacher_id',sa.Integer(),nullable=True))
    op.create_foreign_key('fk_students_meeting_teacher','students','teachers',['meeting_teacher_id'],['id'])


def downgrade():
    op.drop_constraint('fk_students_meeting_teacher','students',type_='foreignkey')
    op.drop_column('students','meeting_teacher_id')
    op.drop_column('students','meeting_url')
