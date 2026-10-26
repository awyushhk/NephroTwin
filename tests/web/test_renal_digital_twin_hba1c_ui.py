from pathlib import Path


PAGE = Path(__file__).resolve().parents[2] / "web" / "src" / "app" / "renal-digital-twin" / "page.tsx"
COMPONENTS_DIR = PAGE.parent / "components"


def _load_ui_source() -> str:
    parts = [PAGE.read_text(encoding="utf-8")]
    if COMPONENTS_DIR.exists():
        for comp in sorted(COMPONENTS_DIR.glob("*.tsx")):
            parts.append(comp.read_text(encoding="utf-8"))
    return "\n".join(parts)


def test_hba1c_is_registered_for_summary_and_measurement_selectors():
    source = _load_ui_source()
    assert 'hba1c: {' in source
    assert 'label: "HbA1c (%)"' in source
    assert 'unit: "%"' in source
    assert "Object.entries(specs).map" in source
    assert "item?.count ?? 0" in source
    assert "item?.latest ? `${item.latest.value}` : \"—\"" in source


def test_hba1c_chart_uses_selected_measurement_query_and_has_empty_state():
    source = _load_ui_source()
    assert "measurement_type=${encodeURIComponent(measurementFilter)}" in source
    assert "limit=500&offset=0&recent=true" in source
    assert "No {specs[measure]?.short ?? measure} observations in this history" in source
    assert "No {selectedMeasurement.label.toLowerCase()} observations are" in source
    assert 'row.measurement_type === measurementFilter' in source
