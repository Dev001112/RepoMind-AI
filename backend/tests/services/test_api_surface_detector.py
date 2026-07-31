from pathlib import Path

from app.services.repository.detectors.api_surface_detector import ApiSurfaceDetector


def test_flask_routes_detected(tmp_path: Path) -> None:
    (tmp_path / "requirements.txt").write_text("flask==3.0.0\n")
    (tmp_path / "app.py").write_text(
        "from flask import Flask\n"
        "app = Flask(__name__)\n\n"
        "@app.route('/health')\n"
        "def health():\n"
        "    return 'ok'\n\n"
        "@app.get('/items')\n"
        "def items():\n"
        "    return []\n"
    )

    result = ApiSurfaceDetector().detect(tmp_path)

    paths = {e.path for e in result.endpoints}
    assert "/health" in paths
    assert "/items" in paths


def test_no_web_framework_skips_scan_entirely(tmp_path: Path) -> None:
    (tmp_path / "script.py").write_text("@app.route('/should-not-be-found')\ndef x(): pass\n")

    result = ApiSurfaceDetector().detect(tmp_path)

    assert result.endpoints == []
