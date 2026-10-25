from pathlib import Path

from data_pipeline.extend_mimic_renal_measurements import _map_items
from data_pipeline.mimic_renal_cohort import parse_timestamp


def _dictionary_dir():
    path = Path(__file__).resolve().parents[2] / ".test-hba1c-dictionary"
    path.mkdir(exist_ok=True)
    (path / "d_labitems.csv").write_text(
        "itemid,label,fluid,category\n"
        "50852,% Hemoglobin A1c,Blood,Chemistry\n"
        "50854,Absolute A1c,Blood,Chemistry\n"
        "51631,Glycated Hemoglobin,Blood,Chemistry\n",
        encoding="utf-8",
    )
    return path


def test_hba1c_extension_accepts_only_explicit_percent_item():
    path = _dictionary_dir()
    try:
        mapped = _map_items(path)
        assert mapped["50852"]["label"] == "% Hemoglobin A1c"
        assert mapped["50854"]["label"] == "Absolute A1c"
        assert mapped["51631"]["label"] == "Glycated Hemoglobin"
    except ValueError as exc:
        raise AssertionError("expected exact audited dictionary definition") from exc
    finally:
        (path / "d_labitems.csv").unlink(missing_ok=True)
        path.rmdir()


def test_hba1c_extension_refuses_dictionary_label_drift():
    path = _dictionary_dir()
    (path / "d_labitems.csv").write_text(
        "itemid,label,fluid,category\n50852,Absolute A1c,Blood,Chemistry\n",
        encoding="utf-8",
    )
    try:
        _map_items(path)
    except ValueError as exc:
        assert "audited exact" in str(exc)
    else:
        raise AssertionError("unexpected dictionary definition must be rejected")
    finally:
        (path / "d_labitems.csv").unlink(missing_ok=True)
        path.rmdir()


def test_source_timestamp_wall_clock_is_preserved():
    source = "2214-08-03 08:08:00"
    parsed = parse_timestamp(source)
    assert parsed is not None
    assert parsed.isoformat(sep=" ") == source
