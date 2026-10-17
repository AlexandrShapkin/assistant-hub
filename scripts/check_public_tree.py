"""Read-only hygiene check of tracked paths (or tracked plus untracked for bootstrap).

Prints paths and categories only, never matched content. This is a heuristic,
not a secret scanner or a guarantee that a tree is safe to publish.
"""
from pathlib import Path, PurePosixPath
import argparse
import re
import subprocess

ROOT = Path(__file__).resolve().parents[1]
BLOCKED_SUFFIXES = {".db", ".sqlite", ".sqlite3", ".pem", ".key", ".p12", ".pfx", ".session"}


def unsafe_path(name: str) -> bool:
    path = PurePosixPath(name)
    return (path.is_absolute() or ".." in path.parts
            or any(part in {".aws", ".codex", ".agents", "personal-data", "data", "__pycache__"}
                   for part in path.parts)
            or any(part == ".env" or part.startswith(".env.") for part in path.parts)
            or path.suffix.lower() in BLOCKED_SUFFIXES
            or any(word in path.name.lower() for word in ("credentials", "secrets", ".session", ".sqlite", ".db-")))


def sensitive_content(data: bytes) -> bool:
    return bool(re.search(rb"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----", data)
                or re.search(rb"(?im)^\s*(?:api_key|access_token|password)\s*[:=]\s*['\"]?[^\s'\"]{8,}", data))


def scan(include_untracked: bool = False) -> list[str]:
    command = ["git", "ls-files", "-z", "--cached"]
    if include_untracked:
        command += ["--others", "--exclude-standard"]
    names = subprocess.check_output(command, cwd=ROOT).decode().split("\0")
    findings = []
    for name in sorted(set(filter(None, names))):
        if unsafe_path(name):
            findings.append(f"{name}: prohibited path")
            continue
        path = ROOT / name
        if path.is_symlink():
            findings.append(f"{name}: symlink requires manual review")
        elif not path.is_file():
            findings.append(f"{name}: unavailable file")
        elif path.stat().st_size > 1_000_000:
            findings.append(f"{name}: oversized file requires manual review")
        elif sensitive_content(path.read_bytes()):
            findings.append(f"{name}: potential secret")
    return findings


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--include-untracked", action="store_true")
    args = parser.parse_args()
    findings = scan(args.include_untracked)
    print("\n".join(findings) if findings else "Public-tree heuristic: clean")
    raise SystemExit(bool(findings))
