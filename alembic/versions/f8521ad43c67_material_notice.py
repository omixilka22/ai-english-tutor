"""Track the disposable teacher analysis notice across restarts."""
from alembic import op
import sqlalchemy as sa
revision='f8521ad43c67'
down_revision='e7410fc32b56'
branch_labels=None
depends_on=None


def upgrade():
    op.add_column('users',sa.Column('material_notice_id',sa.BigInteger(),nullable=True))


def downgrade():
    op.drop_column('users','material_notice_id')
