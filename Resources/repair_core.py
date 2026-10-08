"""Local V2 cache checks and recoverable link updates; no plugin execution."""

import json
import os
from pathlib import Path
import re
import uuid
import hashlib


def file_digest(path):
    digest=hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024*1024), b''):
            digest.update(block)
    return digest.digest()


def _manifest(root):
    try:
        data = json.loads((root / '.codex-plugin/plugin.json').read_text())
        return data if isinstance(data, dict) else None
    except (OSError, ValueError):
        return None


def _local_reference(root, value):
    if not isinstance(value, str) or not value.startswith('./'):
        return None
    candidate = root / value
    try:
        candidate.resolve().relative_to(root.resolve())
    except (ValueError, OSError):
        return None
    return candidate


def cache_ready(name, root, system_name, source=None, ignored_files=()):
    """Structural readiness only. Authoritative same-version source wins."""
    root = Path(root)
    manifest = _manifest(root)
    if not manifest or manifest.get('name') != name or not manifest.get('version'):
        return False
    if system_name == 'darwin' and name in ('browser', 'chrome', 'computer-use', 'unified-computer-use'):
        found_payload = False
        for key in ('skills', 'mcpServers'):
            value = manifest.get(key)
            if value is None:
                continue
            values = value if isinstance(value, list) else [value]
            for reference in values:
                path = _local_reference(root, reference)
                if path is None or not path.exists():
                    return False
                if path.is_dir():
                    if not any(p.is_file() and p.stat().st_size for p in path.rglob('*')):
                        return False
                elif not path.is_file() or not path.stat().st_size:
                    return False
                found_payload = True
        if not found_payload:
            return False
    if system_name == 'windows':
        required = {
            'browser': ['scripts/browser-client.mjs'],
            'chrome': ['scripts/browser-client.mjs',
                       'extension-host/windows/x64/extension-host.exe'],
            'computer-use': ['scripts/computer-use-client.mjs',
                             'node_modules/@oai/sky/bin/windows/codex-computer-use.exe'],
        }.get(name, [])
        if not all((root / item).is_file() for item in required):
            return False

    if source is not None:
        source = Path(source)
        original = _manifest(source)
        if original and original.get('name') == name and original.get('version') == manifest['version']:
            # Check the real source inventory, not one hard-coded macOS layout.
            for item in source.rglob('*'):
                destination = root / item.relative_to(source)
                if str(item.relative_to(source)) in ignored_files:
                    if not destination.is_file() or destination.is_symlink():return False
                    continue
                try:
                    if item.is_symlink():
                        if not destination.is_symlink() or os.readlink(item) != os.readlink(destination):
                            return False
                    elif item.is_dir():
                        if not destination.is_dir() or destination.is_symlink():
                            return False
                    elif item.is_file():
                        if not destination.is_file() or destination.is_symlink():
                            return False
                        if item.stat().st_size != destination.stat().st_size:
                            return False
                        if file_digest(item) != file_digest(destination):
                            return False
                        if item.stat().st_mode & 0o111 and not destination.stat().st_mode & 0o111:
                            return False
                except OSError:
                    return False
            return True

    # Missing matching source leaves completeness unproven: no rewrite/fallback.
    if system_name == 'darwin' and name in ('browser', 'chrome', 'computer-use', 'unified-computer-use'):
        return False
    return True


def numeric_version(root):
    """Compare explicit numeric versions only; unknown/prerelease order is not guessed."""
    manifest = _manifest(Path(root))
    value = manifest.get('version') if manifest else None
    if not isinstance(value, str) or not re.fullmatch(r'\d+(?:\.\d+)+', value):
        return None
    return tuple(int(part) for part in value.split('.'))


def select_cached_target(base, candidates):
    base = Path(base)
    candidates = list(candidates)
    latest = base / 'latest'
    if latest.is_symlink():
        current = latest.resolve()
        for item in candidates:
            if item.resolve() == current:
                return item
    if not candidates:
        return None
    keys = [numeric_version(item) for item in candidates]
    if any(key is None for key in keys):
        return None
    width = max(len(key) for key in keys)
    padded = [key + (0,) * (width - len(key)) for key in keys]
    highest = max(padded)
    matches = [item for item, key in zip(candidates, padded) if key == highest]
    return matches[0] if len(matches) == 1 else None


def replace_latest(base, target, backup_factory, replace=os.replace):
    """Stage a link first; retain real directories and restore on replacement failure."""
    base, target = Path(base), Path(target)
    if not target.is_dir() or target.is_symlink() or target.parent.resolve() != base.resolve():
        raise ValueError('latest target must be a real direct-child cache directory')
    latest = base / 'latest'
    temporary = base / ('.latest-repair-' + uuid.uuid4().hex)
    backup = None
    try:
        temporary.symlink_to(target.name)
        if latest.exists() and not latest.is_symlink():
            backup = Path(backup_factory(latest))
            if backup.exists() or backup.is_symlink():
                raise FileExistsError('backup destination already exists')
            replace(latest, backup)
        try:
            replace(temporary, latest)
        except OSError:
            if backup is not None:
                replace(backup, latest)
            raise
    finally:
        if temporary.is_symlink():
            temporary.unlink()
    return backup
