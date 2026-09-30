"""Hide deleted lessons while preserving their recurrence slot.

Revision ID: 9d8e2a7f4b10
Revises: 7c1a9b0d5e22
"""
from alembic import op
import sqlalchemy as sa
revision = '9d8e2a7f4b10'
down_revision = '7c1a9b0d5e22'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('lessons',sa.Column('is_deleted',sa.Boolean(),nullable=False,server_default=sa.false()))


def downgrade():
    op.execute("""DO $$ BEGIN
        IF EXISTS (SELECT 1 FROM lessons WHERE is_deleted) THEN
            RAISE EXCEPTION 'Cannot downgrade: this would reveal deleted lessons';
        END IF;
    END $$""")
    op.drop_column('lessons','is_deleted')
