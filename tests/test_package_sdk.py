import importlib.util
import hashlib
import json
from pathlib import Path
import struct
import tarfile
import tempfile
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('packager', Path(__file__).parents[1] / 'scripts/package-sdk.py')
packager = importlib.util.module_from_spec(spec)
spec.loader.exec_module(packager)
spec = importlib.util.spec_from_file_location('publisher', Path(__file__).parents[1] / 'scripts/publish-releases.py')
publisher = importlib.util.module_from_spec(spec)
spec.loader.exec_module(publisher)

def extract(path, destination):
    with tarfile.open(path) as archive:
        archive.extractall(destination, filter='data')


class PackageSDKTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.sdk = self.root / 'android-sdk'
        for api in (35, 36):
            self.write(f'platforms/android-{api}/android.jar', b'jar')
            self.write(f'platforms/android-{api}/source.properties', b'Pkg.Revision=1\n')
        for version in ('35.0.0', '36.0.0'):
            self.write(f'build-tools/{version}/source.properties', f'Pkg.Revision={version}\n'.encode())
            self.write(f'build-tools/{version}/package.xml', b'<metadata/>')
            for name in ('aapt2', 'aidl', 'zipalign'):
                self.elf(f'build-tools/{version}/{name}')
            for name in ('d8', 'apksigner'):
                self.write(f'build-tools/{version}/{name}', b'#!/bin/sh\n', 0o755)
        self.write('platform-tools/source.properties', b'Pkg.Revision=36.0.0\n')
        self.elf('platform-tools/adb')
        self.write('cmdline-tools/source.properties', b'Pkg.Revision=19.0\n')
        self.write('cmdline-tools/bin/sdkmanager', b'#!/bin/sh\n', 0o755)
        self.write('licenses/android-sdk-license', b'license')

    def write(self, name, data, mode=0o644):
        file = self.sdk / name
        file.parent.mkdir(parents=True, exist_ok=True)
        file.write_bytes(data)
        file.chmod(mode)
        return file

    def elf(self, name, machine=183):
        return self.write(name, b'\x7fELF\x02\x01' + b'\0' * 12 + struct.pack('<H', machine), 0o755)

    def test_versioned_releases_have_exact_assets_and_equivalent_contents(self):
        destination = self.root / 'dist'
        releases = packager.package(self.sdk, destination, 'aarch64-linux-android')
        self.assertEqual({p.name for p in releases}, {'sdk-35.0.0', 'sdk-36.0.0', 'platform-35', 'platform-36'})
        publisher.validate(destination)
        for major in (35, 36):
            release = destination / f'sdk-{major}.0.0'
            self.assertEqual({p.name for p in release.iterdir()}, {
                'android-sdk.tar.xz', 'build-tools.tar.xz', 'platform-tools.tar.xz',
                'cmdline-tools.tar.xz', 'SHA256SUMS', 'RELEASE.md'})
            full, parts = self.root / f'full-{major}', self.root / f'parts-{major}'
            extract(release / 'android-sdk.tar.xz', full)
            for name in ('build-tools', 'platform-tools', 'cmdline-tools'):
                extract(release / f'{name}.tar.xz', parts)
            extract(destination / f'platform-{major}/platforms.tar.xz', parts)
            files = lambda root: {str(p.relative_to(root)): (p.read_bytes(), p.stat().st_mode & 0o777)
                                  for p in root.rglob('*') if p.is_file()}
            self.assertEqual(files(full), files(parts))
            self.assertEqual([p.name for p in (full / 'android-sdk/build-tools').iterdir()], [f'{major}.0.0'])
            self.assertEqual([p.name for p in (full / 'android-sdk/platforms').iterdir()], [f'android-{major}'])
            self.assertTrue((full / 'android-sdk/cmdline-tools/latest/bin/sdkmanager').exists())
        self.assertEqual(len(packager.components(self.sdk, 'aarch64-linux-android')), 6)
        # Corrupt assets must fail before release inventory or deletion is attempted.
        (destination / 'sdk-35.0.0/build-tools.tar.xz').write_bytes(b'broken')
        with patch.object(publisher, 'releases') as inventory:
            with self.assertRaisesRegex(ValueError, 'Checksum mismatch'):
                publisher.publish(destination, 'example/sdk', 'commit', self.root / 'backup.json')
            inventory.assert_not_called()

    def test_missing_matching_platform_fails_before_any_archive_is_written(self):
        import shutil
        shutil.rmtree(self.sdk / 'platforms/android-35')
        with self.assertRaisesRegex(ValueError, 'needs Platform 35'):
            packager.package(self.sdk, self.root / 'dist', 'aarch64-linux-android')
        self.assertFalse((self.root / 'dist').exists())

    def test_minor_zero_platform_matches_major_build_tools(self):
        (self.sdk / 'platforms/android-35').rename(self.sdk / 'platforms/android-35.0')
        destination = self.root / 'dist'
        packager.package(self.sdk, destination, 'aarch64-linux-android')
        with tarfile.open(destination / 'sdk-35.0.0/android-sdk.tar.xz') as archive:
            self.assertIn('android-sdk/platforms/android-35.0/android.jar', archive.getnames())
        self.assertTrue((destination / 'platform-35.0/platforms.tar.xz').exists())

    def test_changed_release_inventory_prevents_all_deletion(self):
        snapshot = self.root / 'releases.json'
        snapshot.write_text('[]')
        with patch.object(publisher, 'validate', return_value=[self.root / 'sdk-35.0.0']), \
             patch.object(publisher, 'releases', return_value=[{'id': 1, 'tag_name': 'new', 'assets': []}]), \
             patch.object(publisher.subprocess, 'run') as mutate:
            with self.assertRaisesRegex(ValueError, 'changed since backup'):
                publisher.publish(self.root, 'example/sdk', 'commit', snapshot)
            mutate.assert_not_called()

    def test_tag_permission_failure_preserves_existing_releases(self):
        import subprocess
        snapshot = self.root / 'releases.json'
        existing = [{'id': 1, 'tag_name': 'sdk-old', 'assets': []}]
        snapshot.write_text(json.dumps(existing))
        with patch.object(publisher, 'validate', return_value=[self.root / 'platform-35']), \
             patch.object(publisher, 'releases', return_value=existing), \
             patch.object(publisher, 'run', return_value='[[]]'), \
             patch.object(publisher.subprocess, 'run', side_effect=subprocess.CalledProcessError(1, 'gh')) as mutate:
            with self.assertRaises(subprocess.CalledProcessError):
                publisher.publish(self.root, 'example/sdk', 'commit', snapshot)
            self.assertEqual(mutate.call_count, 1)
            self.assertEqual(mutate.call_args.args[0][:3], ['gh', 'api', 'repos/example/sdk/git/refs'])

    def test_rejects_wrong_architecture_and_revision_before_packaging(self):
        self.elf('build-tools/35.0.0/aapt2', machine=62)
        with self.assertRaisesRegex(ValueError, 'Wrong host architecture'):
            packager.components(self.sdk, 'aarch64-linux-android')
        self.elf('build-tools/35.0.0/aapt2')
        self.write('build-tools/35.0.0/source.properties', b'Pkg.Revision=34.0.0\n')
        with self.assertRaisesRegex(ValueError, 'directory/revision mismatch'):
            packager.components(self.sdk, 'aarch64-linux-android')

    def test_official_minor_api_directories_are_preserved(self):
        self.write('platforms/android-37.2/android.jar', b'jar')
        self.write('platforms/android-37.2/source.properties', b'Pkg.Revision=2\n')
        entries = packager.components(self.sdk, 'aarch64-linux-android')
        platform = next(entry for entry in entries if entry[0] == 'platforms;android-37.2')
        self.assertEqual(platform[1].name, 'android-37.2')
        self.assertEqual(platform[2], 'platform-37.2')

    def test_archive_extraction_rejects_path_escape(self):
        archive = self.root / 'unsafe.tar'
        with tarfile.open(archive, 'w') as tar:
            tar.addfile(tarfile.TarInfo('../../escape'))
        with self.assertRaises(tarfile.FilterError):
            extract(archive, self.root / 'safe')
        self.assertFalse((self.root / 'escape').exists())


if __name__ == '__main__':
    unittest.main()
