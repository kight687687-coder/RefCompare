from refcompare.cli import main, _parser


def test_both_commands_accept_optional_analysis_scopes():
    for arguments in (["run", "--dois", "seeds.txt", "--output", "out"], ["analyze", "--input-dir", "bundle"]):
        args = _parser().parse_args([*arguments, "--graph-scope", "all-records", "--ranking-scope", "all-common-nodes"])
        assert args.graph_scope == "all-records"
        assert args.ranking_scope == "all-common-nodes"


def test_help_returns_zero(capsys):
    assert main(["--help"]) == 0
    assert "run" in capsys.readouterr().out


def test_run_requires_crossref_email(monkeypatch, tmp_path, capsys):
    monkeypatch.delenv("CROSSREF_MAILTO", raising=False)
    path = tmp_path / "dois.txt"
    path.write_text("10.1234/example\n", encoding="utf-8")
    assert main(["run", "--dois", str(path), "--output", str(tmp_path / "out")]) == 2
    assert "Crossref email" in capsys.readouterr().err


def test_run_rejects_all_invalid_input(tmp_path, capsys):
    path = tmp_path / "dois.txt"
    path.write_text("invalid\n", encoding="utf-8")
    assert main(["run", "--dois", str(path), "--output", str(tmp_path / "out"), "--mailto", "reader@example.org"]) == 2
    assert "no valid DOI" in capsys.readouterr().err


def test_analyze_reports_missing_bundle(tmp_path, capsys):
    assert main(["analyze", "--input-dir", str(tmp_path / "missing")]) == 2
    assert "run_manifest.json" in capsys.readouterr().err
