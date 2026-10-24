"""Add non-destructive source identity and laboratory provenance columns."""
from alembic import op
import sqlalchemy as sa

revision = "0002_mimic_provenance"
down_revision = "0001_renal_twin"
branch_labels = None
depends_on = None

def upgrade():
    op.add_column("renal_patients", sa.Column("source_system", sa.String(length=32), nullable=True))
    op.add_column("renal_patients", sa.Column("source_patient_id", sa.String(length=64), nullable=True))
    op.create_unique_constraint("uq_patient_source_identity", "renal_patients", ["source_system", "source_patient_id"])
    for name, typ in [
        ("source_system", sa.String(length=32)),
        ("source_subject_id", sa.String(length=64)),
        ("source_observation_id", sa.String(length=64)),
        ("source_item_id", sa.String(length=32)),
        ("source_original_label", sa.String(length=200)),
        ("source_original_value", sa.String(length=200)),
        ("source_original_numeric_value", sa.Float()),
        ("source_original_unit", sa.String(length=32)),
        ("source_charttime_text", sa.String(length=40)),
        ("source_timestamp_timezone", sa.String(length=40)),
        ("source_encounter_id", sa.String(length=64)),
    ]:
        op.add_column("renal_observations", sa.Column(name, typ, nullable=True))
    op.create_unique_constraint("uq_observation_source_identity", "renal_observations", ["source_system", "source_observation_id"])

def downgrade():
    raise RuntimeError("MIMIC provenance migration is forward-only to prevent dropping source identity or provenance data.")
