from data_pipeline import import_mimic_renal_cohort as importer


def _omr_result(**counts):
    return {
        "mode": "dry_run_no_writes",
        "database_writes": False,
        "counts": counts,
    }


def test_omr_dry_run_cli_accepts_its_count_schema(monkeypatch, capsys):
    monkeypatch.setattr(
        importer,
        "import_omr_bp_file",
        lambda *args, **kwargs: _omr_result(
            source_readings=96450,
            component_rows_expected=192900,
            conflicts=0,
            invalid_rows=0,
        ),
    )

    result = importer.main(["--omr-bp-file", "observations.csv", "--omr-cohort-file", "patients.csv"])

    assert result == 0
    output = capsys.readouterr().out
    assert '"database_writes": false' in output
    assert "Dry run only: no database records were changed." in output


def test_omr_dry_run_cli_returns_failure_for_conflicts_or_invalid_rows(monkeypatch):
    monkeypatch.setattr(
        importer,
        "import_omr_bp_file",
        lambda *args, **kwargs: _omr_result(conflicts=1, invalid_rows=0),
    )
    assert importer.main(["--omr-bp-file", "observations.csv", "--omr-cohort-file", "patients.csv"]) == 1

