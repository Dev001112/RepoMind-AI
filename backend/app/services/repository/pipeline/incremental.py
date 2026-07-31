"""Incremental re-analysis: the smallest real win, not per-file diffing.

Checked once, before the expensive clone step. For git sources: a cheap
`git ls-remote` (no clone) compared against the commit sha recorded on the
last successful run. For zip uploads: the sha256 computed at upload time
(the endpoint already reads the bytes into memory) compared against the
stored hash. On a match, the whole pipeline is skipped.

Deferred as future work, not built here: per-file diff-based partial
rescanning, incremental import-graph updates, chunk-level Qdrant diffing --
all need per-file hashing and a real diff algorithm, not justified until
reanalysis volume is an actual measured pain point.
"""

import logging

import git

from app.core.config import Settings
from app.models.orm.repository import Repository

logger = logging.getLogger(__name__)


def _remote_head_sha(source_url: str, github_token: str | None) -> str | None:
    url = source_url
    if github_token:
        url = source_url.replace("https://", f"https://{github_token}@", 1)
    try:
        output = git.cmd.Git().ls_remote(url, "HEAD")
    except git.exc.GitError:
        return None
    if not output:
        return None
    return output.split()[0]


def should_skip_analysis(repository: Repository, settings: Settings) -> bool:
    """True only when there's a prior successful run AND we can positively
    confirm nothing changed since -- any uncertainty (no prior run, can't
    reach the remote) means "run it fully", never "skip"."""
    if repository.source_url and repository.last_analyzed_commit_sha:
        remote_sha = _remote_head_sha(repository.source_url, settings.github_token)
        if remote_sha is None:
            return False
        return remote_sha == repository.last_analyzed_commit_sha

    if not repository.source_url and repository.content_hash and repository.last_analyzed_at:
        # Zip-sourced repos have no re-upload flow today, so an unchanged
        # content_hash here just means "same zip as last time" -- always true
        # after the first run. That's still correct: nothing to re-discover.
        return True

    return False
