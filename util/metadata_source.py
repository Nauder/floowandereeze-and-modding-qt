"""Defaults and validation shared by metadata downloaders and Configuration."""

import json
import re

DEFAULT_METADATA_REPOSITORY = "Nauder/floowandereeze-and-modding-etl"
DEFAULT_METADATA_BRANCH = ""  # Preserve GitHub's current repository-default behavior.


def normalize_metadata_source(repository, branch=""):
    """Accept an owner/repository and an optional GitHub branch/ref."""
    repository = repository.strip()
    branch = branch.strip()
    if not re.fullmatch(r"[A-Za-z0-9-]+/[A-Za-z0-9_.-]+", repository):
        raise ValueError(
            "Repository must use owner/repository format, for example "
            + DEFAULT_METADATA_REPOSITORY
            + "."
        )
    owner, repo = repository.split("/")
    if len(owner) > 39 or len(repo) > 100 or repo in {".", ".."}:
        raise ValueError("Invalid GitHub repository name.")
    if len(branch) > 255 or any(char.isspace() or ord(char) < 32 for char in branch):
        raise ValueError(
            "Branch must be a name/ref without whitespace, or blank for the repository default."
        )
    return repository, branch


def metadata_source_key(repository, branch):
    """Track successful sources independently of their metadata version dates."""
    repository, branch = normalize_metadata_source(repository, branch)
    return json.dumps([repository.casefold(), branch])
