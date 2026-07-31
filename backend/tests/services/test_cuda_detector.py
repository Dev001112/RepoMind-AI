from pathlib import Path

from app.services.repository.detectors.cuda_detector import CudaDetector


def test_cuda_specific_requirement_tag(tmp_path: Path) -> None:
    (tmp_path / "requirements.txt").write_text("torch==2.1.0+cu121\n")

    result = CudaDetector().detect(tmp_path)

    assert (result.gpu_required, result.cuda_required) == (True, True)


def test_cpu_capable_framework_without_cuda_marker(tmp_path: Path) -> None:
    (tmp_path / "requirements.txt").write_text("tensorflow\n")

    result = CudaDetector().detect(tmp_path)

    assert (result.gpu_required, result.cuda_required) == (True, False)


def test_empty_repo_returns_both_false(tmp_path: Path) -> None:
    result = CudaDetector().detect(tmp_path)
    assert (result.gpu_required, result.cuda_required) == (False, False)


def test_missing_path_returns_both_false(tmp_path: Path) -> None:
    missing = tmp_path / "does_not_exist"
    result = CudaDetector().detect(missing)
    assert (result.gpu_required, result.cuda_required) == (False, False)


def test_cuda_base_image_dockerfile(tmp_path: Path) -> None:
    (tmp_path / "Dockerfile").write_text(
        "FROM nvidia/cuda:12.1.0-base-ubuntu22.04\nRUN echo hi\n"
    )

    result = CudaDetector().detect(tmp_path)

    assert (result.gpu_required, result.cuda_required) == (True, True)


def test_ajax_does_not_false_positive_as_jax(tmp_path: Path) -> None:
    # Regression: "jax" as a bare substring also matches inside "AJAX", which shows
    # up in totally unrelated web-project manifests/docs (found via a real Flask scan).
    (tmp_path / "pyproject.toml").write_text(
        'description = "Demonstrates making AJAX requests to Flask."\n'
    )

    result = CudaDetector().detect(tmp_path)

    assert (result.gpu_required, result.cuda_required) == (False, False)


def test_torchvision_is_still_caught_as_a_weak_gpu_signal(tmp_path: Path) -> None:
    (tmp_path / "requirements.txt").write_text("torchvision==0.16.0\n")

    result = CudaDetector().detect(tmp_path)

    assert (result.gpu_required, result.cuda_required) == (True, False)
