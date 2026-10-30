#!/usr/bin/env python3
"""Back up release metadata and every asset before the explicitly requested migration."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--repo', required=True)
parser.add_argument('--dest', type=Path, required=True)
args = parser.parse_args()
pages = json.loads(subprocess.check_output(['gh', 'api', '--paginate', '--slurp',
                                           f'repos/{args.repo}/releases?per_page=100'], text=True))
releases = [release for page in pages for release in page]
args.dest.mkdir(parents=True, exist_ok=True)
(args.dest / 'releases.json').write_text(json.dumps(releases, indent=2))
for release in releases:
    tag = release['tag_name']
    if '/' in tag or tag in ('.', '..'):
        raise ValueError(f'Unsupported backup tag: {tag}')
    directory = args.dest / tag
    directory.mkdir()
    if release['assets']:
        subprocess.run(['gh', 'release', 'download', tag, '--repo', args.repo, '--dir', str(directory)], check=True)
    for asset in release['assets']:
        path = directory / asset['name']
        if path.stat().st_size != asset['size']:
            raise ValueError(f'Backup size mismatch: {path}')
        if asset.get('digest', '').startswith('sha256:'):
            with path.open('rb') as stream:
                actual = hashlib.file_digest(stream, 'sha256').hexdigest()
            if actual != asset['digest'][7:]:
                raise ValueError(f'Backup digest mismatch: {path}')
print(f'Backed up {len(releases)} releases', flush=True)
