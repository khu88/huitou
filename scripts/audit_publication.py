#!/usr/bin/env python3
"""Check proposed Git files for local runtime data and private implementations.

No content or secrets are printed. --staged inspects index blobs, not worktree
copies. This is a focused release guard, not a complete secret/security audit.
"""
import argparse
from pathlib import Path, PurePosixPath
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
PRIVATE_PREFIXES = ('.local/', 'dist/', 'research/qa/', 'research/evidence/',
                    'node_modules/', '.git/')
PRIVATE_NAMES = {'STATUS.md', 'HANDOFF.md', '.DS_Store'}
IMPLEMENTATIONS = [
    re.compile(r'\bdef\s+(?:promote_admin|admin_stats|list_users|set_user_active)\s*\('),
    re.compile(r'\b(?:async\s+)?function\s+loadAdmin\s*\('),
    re.compile(r'\badmin-(?:panel|users|stats|metrics|table)\b'),
    re.compile(r'["\']/api/admin/(?:users|stats)'),
]
SECRETS = [
    re.compile(r'-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----'),
    re.compile(r'\bgh[pousr]_[A-Za-z0-9]{36,}\b'),
    re.compile(r'\bgithub_pat_[A-Za-z0-9_]{40,}\b'),
    re.compile(r'\bsk-(?:proj-)?[A-Za-z0-9_-]{40,}\b'),
]


def inspect_file(name, content, symlink=False):
    """Return reasons, never matching file content."""
    path = PurePosixPath(name)
    reasons = []
    if (name.startswith(PRIVATE_PREFIXES) or path.name in PRIVATE_NAMES
            or '__pycache__' in path.parts or path.suffix in {'.pyc', '.pyo', '.log'}
            or re.search(r'\.(?:sqlite3?|db)(?:-.*)?$', path.name)
            or (path.name.startswith('.env') and path.name != '.env.example')):
        reasons.append('private/runtime file')
    if symlink:
        reasons.append('symlink requires explicit publication review')
    if content.startswith(b'SQLite format 3\x00'):
        reasons.append('database content')
    try:
        text = content.decode('utf-8')
    except UnicodeDecodeError:
        return reasons
    if path.suffix in {'.py', '.js', '.html', '.css', '.mjs'}:
        if any(pattern.search(text) for pattern in IMPLEMENTATIONS):
            reasons.append('private management implementation')
    if any(pattern.search(text) for pattern in SECRETS):
        reasons.append('possible credential/key material')
    if re.search(r'/Users/[A-Za-z0-9._-]+/', text):
        reasons.append('personal absolute filesystem path')
    return reasons


def git(*args):
    return subprocess.check_output(['git', '-C', str(ROOT), *args])


def audit(staged=False):
    if staged:
        names = git('diff', '--cached', '--name-only', '--diff-filter=ACMR', '-z')
    else:
        names = git('ls-files', '--cached', '--others', '--exclude-standard', '-z')
    paths = sorted(set(name.decode('utf-8') for name in names.split(b'\0') if name))
    failures = []
    for name in paths:
        target = ROOT / name
        if staged:
            mode = git('ls-files', '--stage', '--', name).split(b' ', 1)[0]
            content, symlink = git('show', ':' + name), mode == b'120000'
        else:
            symlink = target.is_symlink()
            if not target.exists() and not symlink:
                continue
            content = b'' if symlink else target.read_bytes()
        reasons = inspect_file(name, content, symlink)
        if reasons:
            failures.append((name, reasons))
    for name, reasons in failures:
        print(name + ': ' + ', '.join(reasons))
    print(f'Publication audit: {len(paths)} files, {len(failures)} blocked.')
    return bool(failures)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--staged', action='store_true')
    sys.exit(audit(parser.parse_args().staged))
