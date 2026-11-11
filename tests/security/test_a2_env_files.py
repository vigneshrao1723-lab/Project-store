"""Security audit A2: env files."""

import fnmatch

from .helpers import _docker_ignored, read


def _ignored_by(patterns, path):
    parts = path.split("/")
    for pat in patterns:
        pat = pat.rstrip("/")
        if fnmatch.fnmatch(path, pat) or any(fnmatch.fnmatch(p, pat) for p in parts) or path.startswith(pat + "/"):
            return True
    return False


SECRET_FILES = [".env", ".env.local", ".env.production", ".env.staging"]


def test_a2_env_files_are_git_ignored():
    patterns = [l.strip() for l in read(".gitignore").splitlines() if l.strip() and not l.startswith("#")]
    leaks = [p for p in SECRET_FILES if not _ignored_by(patterns, p)]
    assert not leaks, f".gitignore does not cover {leaks}"


def test_a2_env_files_are_docker_ignored():
    patterns = [l.strip() for l in read(".dockerignore").splitlines() if l.strip() and not l.startswith("#")]
    leaks = [p for p in SECRET_FILES if not _docker_ignored(patterns, p)]
    assert not leaks, f".dockerignore does not cover {leaks}; they would be copied into the image"
