"""Allow complete source timezone provenance descriptions."""
from alembic import op
import sqlalchemy as sa

revision = "0003_timestamp_provenance_length"
down_revision = "0002_mimic_provenance"
branch_labels = None
depends_on = None


def upgrade():
    op.alter_column("renal_observations", "source_timestamp_timezone",
                    existing_type=sa.String(length=40), type_=sa.String(length=80),
                    existing_nullable=True)


def downgrade():
    bind = op.get_bind()
    too_long = bind.execute(sa.text(
        "SELECT count(*) FROM renal_observations WHERE length(source_timestamp_timezone) > 40"
    )).scalar_one()
    if too_long:
        raise RuntimeError("Cannot narrow source_timestamp_timezone: longer provenance values are present.")
    op.alter_column("renal_observations", "source_timestamp_timezone",
                    existing_type=sa.String(length=80), type_=sa.String(length=40),
                    existing_nullable=True)
