#!/usr/bin/env python3
"""Validate all prepared archives before publishing fixed-name, versioned releases."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
import tarfile


def run(*args):
    return subprocess.check_output(args, text=True)


def releases(repo):
    pages = json.loads(run('gh', 'api', '--paginate', '--slurp', f'repos/{repo}/releases?per_page=100'))
    return [release for page in pages for release in page]


def validate(dist):
    prepared = []
    for directory in sorted(dist.iterdir()):
        if not directory.is_dir() or not re.fullmatch(r'(sdk-[0-9]+\.[0-9]+\.[0-9]+|platform-[0-9]+(?:\.[0-9]+)?)', directory.name):
            raise ValueError(f'Unexpected release directory: {directory}')
        expected = {'platforms.tar.xz'} if directory.name.startswith('platform-') else {
            'android-sdk.tar.xz', 'build-tools.tar.xz', 'platform-tools.tar.xz', 'cmdline-tools.tar.xz'}
        if {p.name for p in directory.iterdir()} != expected | {'SHA256SUMS', 'RELEASE.md'}:
            raise ValueError(f'Unexpected assets: {directory}')
        checked = set()
        for line in (directory / 'SHA256SUMS').read_text().splitlines():
            digest, name = line.split('  ', 1)
            if name not in expected or name in checked or not re.fullmatch('[0-9a-f]{64}', digest):
                raise ValueError(f'Invalid checksum entry: {line}')
            with (directory / name).open('rb') as stream:
                if hashlib.file_digest(stream, 'sha256').hexdigest() != digest:
                    raise ValueError(f'Checksum mismatch: {directory / name}')
            with tarfile.open(directory / name) as archive:
                for member in archive:
                    path = Path(member.name)
                    if path.is_absolute() or '..' in path.parts or path.parts[0] != 'android-sdk':
                        raise ValueError(f'Unsafe archive path: {member.name}')
            checked.add(name)
        if checked != expected:
            raise ValueError(f'Missing checksum: {directory}')
        prepared.append(directory)
    if not prepared:
        raise ValueError('No releases to publish')
    return prepared


def publish(dist, repo, commit, replace_snapshot=None):
    prepared = validate(dist)
    existing = releases(repo)
    if replace_snapshot:
        snapshot = json.loads(replace_snapshot.read_text())
        # A migration must not delete new releases/assets published after its backup.
        identity = lambda items: sorted((r['id'], r['tag_name'], sorted((a['id'], a['name'], a['size']) for a in r['assets'])) for r in items)
        if identity(existing) != identity(snapshot):
            raise ValueError('Releases changed since backup; refusing deletion')
        for release in existing:
            subprocess.run(['gh', 'release', 'delete', release['tag_name'], '--repo', repo, '--yes'], check=True)
        existing = []
    tags = {release['tag_name'] for release in existing}
    for directory in prepared:
        if directory.name in tags:
            print(f'Preserving existing release {directory.name}; no assets overwritten', flush=True)
            continue
        assets = sorted(directory.glob('*.tar.xz')) + [directory / 'SHA256SUMS']
        subprocess.run(['gh', 'release', 'create', directory.name, *map(str, assets),
                        '--repo', repo, '--target', commit, '--title', directory.name,
                        '--notes-file', str(directory / 'RELEASE.md'),
                        '--latest' if directory.name == 'sdk-36.0.0' else '--latest=false'], check=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dist', type=Path, required=True)
    parser.add_argument('--repo', required=True)
    parser.add_argument('--commit', required=True)
    parser.add_argument('--replace-snapshot', type=Path)
    parser.add_argument('--verify-only', action='store_true')
    args = parser.parse_args()
    if args.verify_only:
        validate(args.dist)
    else:
        publish(args.dist, args.repo, args.commit, args.replace_snapshot)
