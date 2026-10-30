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
        found.append((f'platforms;android-{api}', directory, f'platform-{api}'))
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
        found.append((f'build-tools;{version}', directory, f'build-tools-{version}'))
    directory = sdk / 'platform-tools'
    if directory.is_dir():
        version = revision(directory)
        if target == 'aarch64-linux-android':
            check_elf(directory / 'adb', 183)
        found.append(('platform-tools', directory, 'platform-tools'))
    for directory in sorted(command_line.glob('*')):
        if not (directory / 'bin/sdkmanager').is_file():
            raise ValueError(f'Incomplete command-line tools: {directory}')
        version = revision(directory)
        found.append((f'cmdline-tools;{version}', directory, 'cmdline-tools'))
    if not any(item[0].startswith('platforms;') for item in found):
        raise ValueError('No Android Platforms')
    if not any(item[0].startswith('build-tools;') for item in found):
        raise ValueError('No Build Tools')
    return found


def archive(sdk, destination, paths, *, bundle=False):
    # Single-platform bundles and parts use a mobile-friendly 16 MiB dictionary.
    print(f'Packaging {destination.name}', flush=True)
    with destination.open('wb') as output:
        compression = ['-T2', '-6', '--lzma2=dict=16MiB']
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


def finish_release(directory, records, description):
    (directory / 'SHA256SUMS').write_text(''.join(
        f'{record["sha256"]}  {record["asset"]}\n' for record in records))
    lines = [description, '', '| Asset | Size |', '| --- | --- |']
    lines += [f'| `{r["asset"]}` | {r["size"] / 1048576:.1f} MiB |' for r in records]
    lines += ['', 'Archives extract into `android-sdk/` and preserve official package metadata.',
              'Android ARM64 host tools; NDK and CMake are distributed separately.', '']
    (directory / 'RELEASE.md').write_text('\n'.join(lines))


def package_platform(sdk, directory, destination):
    api = directory.name.removeprefix('android-')
    if not re.fullmatch(r'[0-9]+(?:\.[0-9]+)?', api) or not (directory / 'android.jar').is_file():
        raise ValueError(f'Incomplete Android Platform: {directory}')
    revision(directory)
    output = destination / f'platform-{api}'
    output.mkdir(parents=True, exist_ok=True)
    licenses = [sdk / 'licenses'] if (sdk / 'licenses').is_dir() else []
    record = archive(sdk, output / 'platforms.tar.xz', [directory, *licenses])
    finish_release(output, [record], f'Android Platform {api}, package revision {revision(directory)}. Architecture-independent official SDK data.')
    return output


def package(sdk, destination, target):
    if target != 'aarch64-linux-android':
        raise ValueError('Folder-named SDK releases are reserved for Android ARM64')
    sdk = sdk.resolve()
    entries = components(sdk, target)
    platforms = {path.name.removeprefix('android-'): path for identifier, path, _ in entries
                 if identifier.startswith('platforms;')}
    build_tools = [path for identifier, path, _ in entries if identifier.startswith('build-tools;')]
    common = [path for identifier, path, _ in entries
              if identifier == 'platform-tools' or identifier.startswith('cmdline-tools;')]
    if len(common) != 2 or not (sdk / 'platform-tools') in common:
        raise ValueError('SDK needs platform-tools and exactly one cmdline-tools version')
    # Validate the entire selection before creating any publishable output.
    selections = []
    for tools in build_tools:
        major = tools.name.split('.')[0]
        api = major if major in platforms else f'{major}.0'
        if api not in platforms:
            raise ValueError(f'Build Tools {tools.name} needs Platform {major} (or {major}.0)')
        selections.append((tools, platforms[api]))
    destination.mkdir(parents=True, exist_ok=True)
    if any(destination.iterdir()):
        raise ValueError(f'Output directory must be empty: {destination}')
    licenses = [sdk / 'licenses'] if (sdk / 'licenses').is_dir() else []
    releases = []
    for tools, platform in selections:
        output = destination / f'sdk-{tools.name}'
        output.mkdir()
        paths = [tools, *common]
        records = []
        for path in paths:
            name = 'build-tools' if path == tools else ('platform-tools' if path.name == 'platform-tools' else 'cmdline-tools')
            records.append(archive(sdk, output / f'{name}.tar.xz', [path, *licenses]))
        records.append(archive(sdk, output / 'android-sdk.tar.xz', [*paths, platform, *licenses], bundle=True))
        finish_release(output, records, f'Android ARM64 SDK: Build Tools {tools.name}; Platform {platform.name.removeprefix("android-")}; Platform Tools {revision(sdk / "platform-tools")}; Command-line Tools {revision(next(p for p in common if p.name != "platform-tools"))}.')
        releases.append(output)
    for platform in platforms.values():
        releases.append(package_platform(sdk, platform, destination))
    return releases


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--sdk', type=Path, required=True)
    parser.add_argument('--dest', type=Path, required=True)
    parser.add_argument('--target', required=True)
    args = parser.parse_args()
    package(args.sdk, args.dest, args.target)
