from pathlib import Path
from typing import ClassVar

from pydantic import BaseModel

from app.services.repository.detectors.base import Detector


class _Result(BaseModel):
    value: int = 0


class _AlwaysFails(Detector[_Result]):
    result_model: ClassVar[type[_Result]] = _Result

    def detect(self, repo_path: Path) -> _Result:
        raise RuntimeError("boom")


class _Succeeds(Detector[_Result]):
    result_model: ClassVar[type[_Result]] = _Result

    def detect(self, repo_path: Path) -> _Result:
        return _Result(value=42)


def test_run_wraps_success_with_no_errors(tmp_path: Path) -> None:
    envelope = _Succeeds().run(tmp_path)

    assert envelope.data == _Result(value=42)
    assert envelope.errors == []
    assert envelope.detector_name == "_Succeeds"
    assert envelope.confidence == 1.0
    assert envelope.detected_at is not None


def test_run_captures_exception_as_error_and_returns_safe_default(tmp_path: Path) -> None:
    envelope = _AlwaysFails().run(tmp_path)

    assert envelope.data == _Result()  # safe default, not a crash
    assert len(envelope.errors) == 1
    assert "boom" in envelope.errors[0]
