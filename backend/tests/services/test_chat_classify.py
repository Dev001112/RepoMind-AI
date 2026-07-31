from app.ai.langgraph.graph import _classify


def _category(question: str) -> str:
    return _classify({"question": question})["category"]


def test_real_security_questions_route_to_security() -> None:
    assert _category("Are there any security vulnerabilities?") == "security"
    assert _category("Is there a SQL injection risk here?") == "security"
    assert _category("How does authentication work?") == "security"
    assert _category("Are there hardcoded secrets or passwords?") == "security"


def test_real_architecture_questions_route_to_architecture() -> None:
    assert _category("Explain the architecture and folder structure.") == "architecture"
    assert _category("How are modules organized in this codebase?") == "architecture"


def test_general_questions_stay_general() -> None:
    assert _category("What does this project do?") == "general"
    assert _category("How do I install this?") == "general"
    assert _category("What are the main dependencies?") == "general"


def test_author_does_not_false_positive_as_auth() -> None:
    # Regression: bare "auth" substring matched inside "author" -- same class of
    # bug as the earlier "jax"-inside-"AJAX" false positive in cuda_detector.py.
    assert _category("Who is the author of this repository?") == "general"


def test_dependency_injection_does_not_false_positive_as_security() -> None:
    # "injection" alone used to match -- now requires a real security phrase
    # ("sql/code/command injection", "injection attack"), so this correctly
    # falls through to general rather than the security-only lens.
    assert _category("How does dependency injection work in this codebase?") == "general"


def test_asterisk_does_not_false_positive_as_risk() -> None:
    assert _category("What is the asterisk used for in this regex?") == "general"
