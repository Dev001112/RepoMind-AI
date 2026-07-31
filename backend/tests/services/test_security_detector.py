from pathlib import Path

from app.services.repository.detectors.security_detector import SecurityDetector


def test_detects_hardcoded_aws_key(tmp_path: Path) -> None:
    (tmp_path / "config.py").write_text('AWS_KEY = "AKIAABCDEFGHIJKLMNOP"\n')

    result = SecurityDetector().detect(tmp_path)

    assert any("AWS access key" in f for f in result.security_findings)


def test_detects_risky_code_patterns(tmp_path: Path) -> None:
    (tmp_path / "app.py").write_text(
        "import subprocess\nsubprocess.run(cmd, shell=True)\neval(user_input)\n"
    )

    result = SecurityDetector().detect(tmp_path)

    findings = " ".join(result.security_findings)
    assert "shell=True" in findings
    assert "eval()" in findings


def test_committed_env_without_gitignore_is_flagged(tmp_path: Path) -> None:
    (tmp_path / ".env").write_text("SECRET=x\n")

    result = SecurityDetector().detect(tmp_path)

    assert any(".env" in f for f in result.security_findings)


def test_committed_env_covered_by_gitignore_is_not_flagged(tmp_path: Path) -> None:
    (tmp_path / ".env").write_text("SECRET=x\n")
    (tmp_path / ".gitignore").write_text(".env\nnode_modules/\n")

    result = SecurityDetector().detect(tmp_path)

    assert result.security_findings == []


def test_clean_repo_has_no_findings(tmp_path: Path) -> None:
    (tmp_path / "app.py").write_text("def add(a, b):\n    return a + b\n")

    assert SecurityDetector().detect(tmp_path).security_findings == []


def test_missing_path_returns_empty(tmp_path: Path) -> None:
    assert SecurityDetector().detect(tmp_path / "nope").security_findings == []


def test_test_fixture_placeholder_password_is_not_flagged(tmp_path: Path) -> None:
    # Regression: found via a real live scan of Flask's own tutorial test fixture
    # -- `def login(self, username="test", password="test")` is not a real secret.
    (tmp_path / "conftest.py").write_text(
        'def login(self, username="test", password="test"):\n    pass\n'
    )

    result = SecurityDetector().detect(tmp_path)

    assert result.security_findings == []


def test_real_looking_hardcoded_password_is_still_flagged(tmp_path: Path) -> None:
    (tmp_path / "config.py").write_text('password = "Tr0ub4dor&3xyz"\n')

    result = SecurityDetector().detect(tmp_path)

    assert any("hardcoded password" in f for f in result.security_findings)
