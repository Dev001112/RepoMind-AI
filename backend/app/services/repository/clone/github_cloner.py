"""Clones a public/private GitHub repo to local disk."""

from pathlib import Path

import git

from app.core.config import Settings
from app.services.repository.clone.base import BaseCloner


class GithubCloner(BaseCloner):
    def __init__(self, github_token: str | None = None) -> None:
        self.github_token = github_token

    @classmethod
    def from_settings(cls, settings: Settings) -> "GithubCloner":
        return cls(github_token=settings.github_token)

    def clone(self, source: str, dest: Path) -> Path:
        """Shallow-clone `source` into `dest` using GitPython, authenticating
        with `self.github_token` (if set) via a token-embedded URL that never
        leaves this method."""
        clone_url = source
        if self.github_token:
            clone_url = source.replace("https://", f"https://{self.github_token}@", 1)

        try:
            git.Repo.clone_from(clone_url, dest, depth=1, single_branch=True)
        except (git.exc.GitCommandError, git.exc.GitError):
            # `from None` suppresses exception chaining: GitCommandError's string
            # form can embed the authenticated (token-bearing) URL, and letting it
            # ride along as __context__ would leak it into any traceback/log.
            raise RuntimeError(f"failed to clone {source}") from None

        return dest
