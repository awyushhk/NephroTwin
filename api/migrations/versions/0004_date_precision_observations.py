"""Support exact-time and date-only renal observations without time fabrication."""
from alembic import op
import sqlalchemy as sa

revision = "0004_date_precision_observations"
down_revision = "0003_timestamp_provenance_length"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "renal_observations",
        sa.Column("timestamp_precision", sa.String(length=16), server_default="exact_time", nullable=False),
    )
    op.add_column("renal_observations", sa.Column("observed_date", sa.Date(), nullable=True))
    op.add_column("renal_observations", sa.Column("source_sequence_number", sa.Integer(), nullable=True))
    # Store the UTC calendar date for indexed date ordering. This does not change
    # the original timestamp or claim a source timezone for legacy observations.
    op.execute(
        "UPDATE renal_observations "
        "SET observed_date = CAST(observed_at AT TIME ZONE 'UTC' AS DATE) "
        "WHERE observed_at IS NOT NULL"
    )
    op.alter_column(
        "renal_observations", "observed_at",
        existing_type=sa.DateTime(timezone=True), nullable=True,
    )
    op.create_check_constraint(
        "ck_observation_timestamp_precision",
        "renal_observations",
        "(timestamp_precision = 'exact_time' AND observed_at IS NOT NULL) OR "
        "(timestamp_precision = 'date_only' AND observed_at IS NULL AND observed_date IS NOT NULL)",
    )
    op.create_check_constraint(
        "ck_observation_timestamp_precision_value",
        "renal_observations",
        "timestamp_precision IN ('exact_time', 'date_only')",
    )
    op.create_index(
        "ix_renal_observations_patient_event_order",
        "renal_observations",
        ["patient_id", "observed_date", "source_sequence_number", "observed_at", "id"],
    )


def downgrade():
    bind = op.get_bind()
    date_only_rows = bind.execute(sa.text(
        "SELECT count(*) FROM renal_observations WHERE timestamp_precision = 'date_only'"
    )).scalar_one()
    if date_only_rows:
        raise RuntimeError("Cannot downgrade while date-only observations exist; converting them to timestamps would invent times.")
    op.drop_index("ix_renal_observations_patient_event_order", table_name="renal_observations")
    op.drop_constraint("ck_observation_timestamp_precision_value", "renal_observations", type_="check")
    op.drop_constraint("ck_observation_timestamp_precision", "renal_observations", type_="check")
    op.alter_column(
        "renal_observations", "observed_at",
        existing_type=sa.DateTime(timezone=True), nullable=False,
    )
    op.drop_column("renal_observations", "source_sequence_number")
    op.drop_column("renal_observations", "observed_date")
    op.drop_column("renal_observations", "timestamp_precision")
