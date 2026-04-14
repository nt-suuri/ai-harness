"""PyGithub client + repo-scoped helpers used by every agent."""

import os
from functools import cache

from github import Github
from github.Repository import Repository

_DEFAULT_REPO = "nt-suuri/ai-harness"


@cache
def _client() -> Github:
    token = os.environ["GITHUB_TOKEN"]
    return Github(token)


def repo(fullname: str | None = None) -> Repository:
    name = fullname or os.environ.get("GH_REPO", _DEFAULT_REPO)
    return _client().get_repo(name)
