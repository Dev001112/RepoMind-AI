from pathlib import Path

from app.services.repository.metadata.readme_parser import ReadmeParser

README_MD = """# MyProject

[![Build Status](https://example.com/badge.svg)](https://example.com)

A tool that does the thing.

## Installation

```
pip install myproject
```

## License

This project is licensed under the terms below.
"""

LICENSE_TEXT = "MIT License\n\nCopyright (c) 2026\n"


def test_full_readme_and_license(tmp_path: Path) -> None:
    (tmp_path / "README.md").write_text(README_MD, encoding="utf-8")
    (tmp_path / "LICENSE").write_text(LICENSE_TEXT, encoding="utf-8")

    result = ReadmeParser().detect(tmp_path)

    assert result.name == "MyProject"
    assert result.description is not None
    assert "A tool that does the thing." in result.description
    assert result.installation_steps == ["pip install myproject"]
    assert result.license == "MIT"
    assert result.has_readme is True
    assert result.has_license_file is True
    assert result.has_contributing is False


def test_no_readme_returns_empty_defaults(tmp_path: Path) -> None:
    result = ReadmeParser().detect(tmp_path)

    assert result.name is None
    assert result.description is None
    assert result.license is None
    assert result.installation_steps == []
    assert result.has_readme is False


def test_readme_without_license_file_falls_back_to_readme_section(tmp_path: Path) -> None:
    readme = (
        "# OtherProj\n\n"
        "Does other things.\n\n"
        "## License\n\n"
        "Released under the Apache License, Version 2.0.\n"
    )
    (tmp_path / "README.md").write_text(readme, encoding="utf-8")

    result = ReadmeParser().detect(tmp_path)

    assert result.name == "OtherProj"
    assert result.license == "Apache-2.0"
    assert result.installation_steps == []


def test_bsd_license_without_the_word_bsd_is_still_recognized(tmp_path: Path) -> None:
    # Regression: real BSD-3-Clause boilerplate (e.g. Flask's actual LICENSE.txt)
    # often never contains the word "BSD" at all.
    (tmp_path / "LICENSE.txt").write_text(
        "Copyright 2010 Pallets\n\n"
        "Redistribution and use in source and binary forms, with or without\n"
        "modification, are permitted provided that the following conditions are\n"
        "met:\n",
        encoding="utf-8",
    )

    result = ReadmeParser().detect(tmp_path)

    assert result.license == "BSD"


def test_contributing_file_is_detected(tmp_path: Path) -> None:
    (tmp_path / "CONTRIBUTING.md").write_text("Please open a PR.\n", encoding="utf-8")

    result = ReadmeParser().detect(tmp_path)

    assert result.has_contributing is True
