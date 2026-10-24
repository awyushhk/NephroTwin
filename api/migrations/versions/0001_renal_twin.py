"""Create persistent renal twin tables."""
from alembic import op
from api.database import Base
from api import models  # register table metadata
from sqlalchemy import inspect

revision = "0001_renal_twin"
down_revision = None
branch_labels = None
depends_on = None

def upgrade():
    # Verify any pre-existing twin tables before creating missing tables/indexes.
    bind = op.get_bind()
    inspector = inspect(bind)
    for table in Base.metadata.sorted_tables:
        if inspector.has_table(table.name):
            actual = {column["name"] for column in inspector.get_columns(table.name)}
            expected = {column.name for column in table.columns}
            missing = expected - actual
            if missing:
                raise RuntimeError(f"Existing table {table.name} is missing expected columns {sorted(missing)}; inspect and back up the database before migration.")
    Base.metadata.create_all(bind=bind, checkfirst=True)

def downgrade():
    # Intentionally non-destructive: patient observations are not removed by downgrade.
    pass
