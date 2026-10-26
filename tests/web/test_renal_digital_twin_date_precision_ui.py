from pathlib import Path


PAGE = Path(__file__).resolve().parents[2] / "web" / "src" / "app" / "renal-digital-twin" / "page.tsx"
COMPONENTS_DIR = PAGE.parent / "components"
TYPES = PAGE.parent / "types.ts"


def _load_ui_source() -> str:
    parts = [PAGE.read_text(encoding="utf-8")]
    if TYPES.exists():
        parts.append(TYPES.read_text(encoding="utf-8"))
    if COMPONENTS_DIR.exists():
        for comp in sorted(COMPONENTS_DIR.glob("*.tsx")):
            parts.append(comp.read_text(encoding="utf-8"))
    return "\n".join(parts)


def test_timeline_renders_date_only_without_showing_a_fabricated_time():
    source = _load_ui_source()
    assert 'timestamp_precision?: "exact_time" | "date_only"' in source
    assert 'if (row.timestamp_precision === "date_only") return formatDate(row.observed_date, false)' in source
    assert 'Date only · seq {row.source_sequence_number}' in source
    assert "Same-day order unresolved" in source
    assert "same-day date-only readings follow source sequence order" in source
    assert "No line is shown because same-day mixed-precision ordering is unresolved." in source
    assert 'chart.points.length > 1 && !hasUnresolvedOrdering' in source
    assert 'trajectoryEligibilityLoading ? "· checking inputs" : trajectoryInputsAvailable ? "· eligible" : "· review required"' in source
    assert 'patients/${patientId}/trajectory' in source
    assert '{simulatorMode === "linear" && eGfrObservations.length > 0 && (' in source
    assert '<MechanisticTrajectoryPlot points={trajectoryResultForPatient.trajectory} metric="egfr"' in source
    assert '<MechanisticTrajectoryPlot points={trajectoryResultForPatient.trajectory} metric="uacr"' in source
    assert 'trajectory/eligibility?baseline_observation_id=' in source
    assert 'disabled={!patientId || !scenarioBase || !trajectoryInputsAvailable || trajectoryEligibilityLoading || trajectoryLoading}' in source
    assert 'id="trajectory-baseline"' in source
    assert 'Example patients' in source
    assert source.index('Example patients') < source.index('aria-labelledby="profile-heading"')
    assert 'recommended-examples' in source
    assert 'function loadExamplePatient(example: ExamplePatient)' in source
    assert 'Broad history' in source
    assert 'ACR + HbA1c' in source
    assert 'eGFR history' in source
    assert 'aria-pressed={patientId === example.id}' in source
    assert 'patientId === example.id ? "Loaded"' not in source
    assert 'freshness_status.replaceAll("_", " ")' in source
    assert 'selectedRows.some((row) => row.timestamp_precision === "date_only")' in source
    assert 'observationCoordinate(row, calendarDateAxis)' in source
