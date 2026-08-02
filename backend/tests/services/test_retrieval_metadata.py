"""Metadata Extractor tests: framework/language/path/symbol/API extraction."""

from app.services.retrieval.metadata import MetadataExtractor, RepoProfile


def test_extracts_language_and_framework_from_profile():
    profile = RepoProfile(languages={"python"}, frameworks={"flask"})
    meta = MetadataExtractor(profile).extract("how does flask handle auth in python?")
    assert meta.language == "python"
    assert meta.framework == "flask"


def test_extracts_file_path():
    meta = MetadataExtractor().extract("where is the file api/auth.py?")
    assert meta.file == "api/auth.py"
    assert meta.directory == "api"
    assert meta.language == "python"


def test_extracts_api_route():
    meta = MetadataExtractor().extract("what does POST /login accept?")
    assert meta.api_route == "/login"
    assert meta.type == "api_endpoint"


def test_extracts_function_symbol():
    meta = MetadataExtractor().extract("what does verify_password() do?")
    assert meta.symbol == "verify_password"
    assert meta.type == "function"


def test_extracts_class_symbol():
    meta = MetadataExtractor().extract("explain the User model class")
    assert meta.type == "class"


def test_unknown_query_yields_empty_metadata():
    meta = MetadataExtractor().extract("tell me about everything")
    assert meta.type is None
    assert meta.language is None
    assert meta.framework is None
    assert meta.file is None
