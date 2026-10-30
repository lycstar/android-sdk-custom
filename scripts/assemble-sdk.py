#!/usr/bin/env python3
"""Assemble ARM64 tools from releases and platforms from Google's SDK Manager."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import tarfile


def run(*arguments):
    return subprocess.check_output(arguments, text=True)


def extract(archive, destination):
    # Python 3.12+ data filter rejects escaping archive paths and unsafe links.
    with tarfile.open(archive) as tar:
        tar.extractall(destination, filter='data')


def assemble(config, repo, work, sdkmanager='sdkmanager'):
    if not re.fullmatch(r'[\w.-]+/[\w.-]+', repo):
        raise ValueError('Invalid GitHub repository')
    target = config['target']
    asset_name = f'android-sdk-{target}.tar.xz'
    sources = []

    def download(tag):
        release = json.loads(run('gh', 'api', f'repos/{repo}/releases/tags/{tag}'))
        asset = next(item for item in release['assets'] if item['name'] == asset_name)
        digest = asset.get('digest') or ''
        if not re.fullmatch(r'sha256:[a-fA-F0-9]{64}', digest):
            raise ValueError(f'{tag}: missing GitHub SHA-256 digest')
        destination = work / 'downloads' / tag
        destination.mkdir(parents=True, exist_ok=True)
        subprocess.run(['gh', 'release', 'download', tag, '--repo', repo, '--pattern', asset_name,
                        '--dir', str(destination), '--clobber'], check=True)
        archive = destination / asset_name
        with archive.open('rb') as stream:
            actual = hashlib.file_digest(stream, 'sha256').hexdigest()
        if actual != digest.removeprefix('sha256:').lower():
            raise ValueError(f'{tag}: SHA-256 mismatch')
        sources.append({'release': tag, 'asset': asset_name, 'sha256': actual})
        return archive

    base = work / 'base'
    extract(download(config['baseRelease']), base)
    sdk = base / 'android-sdk'
    for entry in config['additionalBuildTools']:
        extracted = work / 'components' / entry['release']
        extract(download(entry['release']), extracted)
        source = extracted / 'android-sdk/build-tools' / entry['version']
        if not source.is_dir():
            raise ValueError(f'Missing requested Build Tools: {source}')
        target_directory = sdk / 'build-tools' / entry['version']
        if target_directory.exists():
            raise ValueError(f'Duplicate Build Tools version: {entry["version"]}')
        shutil.move(str(source), target_directory)
    official_platforms = config.get('officialPlatforms', [])
    if official_platforms:
        packages = []
        for api in official_platforms:
            if not re.fullmatch(r'[0-9]+(?:\.[0-9]+)?', str(api)):
                raise ValueError(f'Invalid official Platform API: {api}')
            packages.append(f'platforms;android-{api}')
        # Use the runner's current SDK Manager, not the tools being packaged.
        # It verifies Google's archives and writes the official package.xml.
        subprocess.run([sdkmanager, f'--sdk_root={sdk}', '--install', *packages], check=True)
        for api, identifier in zip(official_platforms, packages):
            properties = (sdk / f'platforms/android-{api}/source.properties').read_text()
            if not re.search(rf'^AndroidVersion.ApiLevel\s*=\s*{re.escape(str(api))}\s*$', properties, re.M):
                raise ValueError(f'Official Platform API mismatch: {api}')
            sources.append({'repository': 'https://dl.google.com/android/repository/repository2-3.xml',
                            'package': identifier,
                            'revision': re.search(r'^Pkg.Revision\s*=\s*(\S+)', properties, re.M)[1]})
    for api in config['requiredPlatforms']:
        if not (sdk / f'platforms/android-{api}/android.jar').is_file():
            raise ValueError(f'Missing Platform API {api}')
    for version in config['requiredBuildTools']:
        if not (sdk / f'build-tools/{version}/source.properties').is_file():
            raise ValueError(f'Missing Build Tools {version}')
    (work / 'sources.json').write_text(json.dumps(sources, indent=2) + '\n')
    return sdk


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', type=Path, default=Path('sdk-bundle.json'))
    parser.add_argument('--repo', required=True)
    parser.add_argument('--work', type=Path, required=True)
    parser.add_argument('--sdkmanager', default='sdkmanager')
    args = parser.parse_args()
    assemble(json.loads(args.config.read_text()), args.repo, args.work.resolve(), args.sdkmanager)
