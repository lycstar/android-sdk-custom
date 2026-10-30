#!/usr/bin/env python3
"""Package one prepared SDK tree as a bundle and independently installable components."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import tarfile


def revision(directory):
    text = (directory / 'source.properties').read_text()
    match = re.search(r'^Pkg\.Revision\s*=\s*(\S+)', text, re.M)
    if not match:
        raise ValueError(f'Missing Pkg.Revision: {directory}')
    return match[1]


def sha256(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def check_elf(path, machine):
    with path.open('rb') as stream:
        header = stream.read(20)
    if header[:4] != b'\x7fELF' or len(header) < 20:
        raise ValueError(f'Expected ELF executable: {path}')
    byteorder = 'little' if header[5] == 1 else 'big'
    if int.from_bytes(header[18:20], byteorder) != machine:
        raise ValueError(f'Wrong host architecture: {path}')
    if not os.access(path, os.X_OK):
        raise ValueError(f'Not executable: {path}')


def components(sdk, target):
    # Match Google's standard command-line tools layout before either packaging path.
    command_line = sdk / 'cmdline-tools'
    if (command_line / 'bin').is_dir():
        temporary = sdk / '.cmdline-tools-packaging'
        command_line.rename(temporary)
        command_line.mkdir()
        temporary.rename(command_line / 'latest')
    found = []
    for directory in sorted((sdk / 'platforms').glob('android-*')):
        api = directory.name.removeprefix('android-')
        if not re.fullmatch(r'[0-9]+(?:\.[0-9]+)?', api) or not (directory / 'android.jar').is_file():
            raise ValueError(f'Incomplete Android Platform: {directory}')
        revision(directory)
        found.append((f'platforms;android-{api}', directory, f'android-platform-{api}'))
    for directory in sorted((sdk / 'build-tools').glob('*')):
        version = revision(directory)
        if version != directory.name:
            raise ValueError(f'Build Tools directory/revision mismatch: {directory}: {version}')
        for name in ('aapt2', 'aidl', 'zipalign', 'd8', 'apksigner'):
            if not (directory / name).is_file():
                raise ValueError(f'Missing {name}: {directory}')
        if target == 'aarch64-linux-android':
            for name in ('aapt2', 'aidl', 'zipalign'):
                check_elf(directory / name, 183)
        found.append((f'build-tools;{version}', directory, f'android-build-tools-{version}-{target}'))
    directory = sdk / 'platform-tools'
    if directory.is_dir():
        version = revision(directory)
        if target == 'aarch64-linux-android':
            check_elf(directory / 'adb', 183)
        found.append(('platform-tools', directory, f'android-platform-tools-{version}-{target}'))
    for directory in sorted(command_line.glob('*')):
        if not (directory / 'bin/sdkmanager').is_file():
            raise ValueError(f'Incomplete command-line tools: {directory}')
        version = revision(directory)
        found.append((f'cmdline-tools;{version}', directory, f'android-command-line-tools-{version}-{target}'))
    if not any(item[0].startswith('platforms;') for item in found):
        raise ValueError('No Android Platforms')
    if not any(item[0].startswith('build-tools;') for item in found):
        raise ValueError('No Build Tools')
    return found


def archive(sdk, destination, paths, *, bundle=False):
    # The bundle benefits from cross-version deduplication (e.g. platform data).
    # Use the existing SDK's 256 MiB extraction dictionary; component archives
    # use 16 MiB, since they do not contain multiple platform/tool versions.
    print(f'Packaging {destination.name}', flush=True)
    with destination.open('wb') as output:
        compression = ['-T1', '-9', '--lzma2=dict=256MiB'] if bundle else ['-T2', '-6', '--lzma2=dict=16MiB']
        compressor = subprocess.Popen(['xz', *compression],
                                      stdin=subprocess.PIPE, stdout=output)
        try:
            with tarfile.open(fileobj=compressor.stdin, mode='w|', format=tarfile.PAX_FORMAT) as tar:
                for path in paths:
                    tar.add(path, arcname='android-sdk/' + str(path.relative_to(sdk)))
            compressor.stdin.close()
            if compressor.wait() != 0:
                raise RuntimeError(f'XZ compression failed: {destination}')
        except BaseException:
            compressor.kill()
            compressor.wait()
            destination.unlink(missing_ok=True)
            raise
    digest = sha256(destination)
    return {'asset': destination.name, 'size': destination.stat().st_size, 'sha256': digest}


def package(sdk, destination, target):
    sdk = sdk.resolve()
    destination.mkdir(parents=True, exist_ok=True)
    entries = components(sdk, target)
    licenses = [sdk / 'licenses'] if (sdk / 'licenses').is_dir() else []
    manifest = {'schemaVersion': 1, 'target': target, 'components': []}
    for identifier, directory, name in entries:
        record = archive(sdk, destination / f'{name}.tar.xz', [directory, *licenses])
        record.update(id=identifier, version=revision(directory),
                      installPath=str(directory.relative_to(sdk)))
        manifest['components'].append(record)
    # Bundle and component archives contain exactly the same prepared directories.
    manifest['bundle'] = archive(sdk, destination / f'android-sdk-{target}.tar.xz',
                                 [item[1] for item in entries] + licenses, bundle=True)
    manifest_path = destination / f'sdk-components-{target}.json'
    manifest_path.write_text(json.dumps(manifest, indent=2) + '\n')
    files = sorted(destination.glob('*.tar.xz')) + [manifest_path]
    (destination / f'SHA256SUMS-{target}').write_text(''.join(
        f'{sha256(path)}  {path.name}\n'
        for path in files))
    lines = ['| Component | Version | Download |', '| --- | --- | --- |']
    for record in manifest['components']:
        lines.append(f'| `{record["id"]}` | {record["version"]} | {record["size"] / 1048576:.1f} MiB |')
    lines += ['', f'Full SDK bundle: **{manifest["bundle"]["size"] / 1048576:.1f} MiB**.',
              'Download the full bundle for initialization, or only a missing component.',
              'All archives extract into the same `android-sdk/` root. Existing versions are retained by the Flit installer.',
              'NDK and CMake are distributed separately.', '']
    (destination / f'RELEASE-{target}.md').write_text('\n'.join(lines))
    return manifest


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--sdk', type=Path, required=True)
    parser.add_argument('--dest', type=Path, required=True)
    parser.add_argument('--target', required=True)
    args = parser.parse_args()
    package(args.sdk, args.dest, args.target)
