"""Explicit teacher confirmation; do not infer attendance from old statuses."""
from alembic import op
import sqlalchemy as sa
revision='e7410fc32b56'
down_revision='d6309eb21a45'
branch_labels=None
depends_on=None


def upgrade():
    op.add_column('lessons',sa.Column('conducted_at',sa.DateTime(timezone=True),nullable=True))
    op.add_column('lessons',sa.Column('conducted_by',sa.Integer(),nullable=True))
    op.create_foreign_key('fk_lessons_conducted_by','lessons','teachers',['conducted_by'],['id'])


def downgrade():
    op.drop_constraint('fk_lessons_conducted_by','lessons',type_='foreignkey')
    op.drop_column('lessons','conducted_by')
    op.drop_column('lessons','conducted_at')
