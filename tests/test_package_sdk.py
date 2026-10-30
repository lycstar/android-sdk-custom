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
spec = importlib.util.spec_from_file_location('assembler', Path(__file__).parents[1] / 'scripts/assemble-sdk.py')
assembler = importlib.util.module_from_spec(spec)
spec.loader.exec_module(assembler)


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

    def test_bundle_and_parts_are_equivalent_and_keep_metadata_and_permissions(self):
        destination = self.root / 'dist'
        manifest = packager.package(self.sdk, destination, 'aarch64-linux-android')
        self.assertEqual(len(manifest['components']), 6)
        full = self.root / 'full'
        parts = self.root / 'parts'
        assembler.extract(destination / manifest['bundle']['asset'], full)
        for record in manifest['components']:
            archive = destination / record['asset']
            self.assertEqual(hashlib.sha256(archive.read_bytes()).hexdigest(), record['sha256'])
            self.assertEqual(archive.stat().st_size, record['size'])
            assembler.extract(archive, parts)
        files = lambda root: {str(p.relative_to(root)): (p.read_bytes(), p.stat().st_mode & 0o777)
                              for p in root.rglob('*') if p.is_file()}
        self.assertEqual(files(full), files(parts))
        self.assertTrue((parts / 'android-sdk/cmdline-tools/latest/bin/sdkmanager').exists())
        self.assertEqual((parts / 'android-sdk/build-tools/35.0.0/package.xml').read_bytes(), b'<metadata/>')
        saved = json.loads((destination / 'sdk-components-aarch64-linux-android.json').read_text())
        self.assertEqual(saved, manifest)
        self.assertIn('build-tools;35.0.0', (destination / 'RELEASE-aarch64-linux-android.md').read_text())
        # Already standardized layouts can be packaged again without another migration.
        self.assertEqual(len(packager.components(self.sdk, 'aarch64-linux-android')), 6)

    def test_rejects_wrong_architecture_and_revision_before_packaging(self):
        self.elf('build-tools/35.0.0/aapt2', machine=62)
        with self.assertRaisesRegex(ValueError, 'Wrong host architecture'):
            packager.components(self.sdk, 'aarch64-linux-android')
        self.elf('build-tools/35.0.0/aapt2')
        self.write('build-tools/35.0.0/source.properties', b'Pkg.Revision=34.0.0\n')
        with self.assertRaisesRegex(ValueError, 'directory/revision mismatch'):
            packager.components(self.sdk, 'aarch64-linux-android')

    def test_assembler_verifies_source_digests_and_merges_only_requested_build_tools(self):
        # Existing release bundles may contain overlapping components. Only the requested
        # Build Tools from additions should enter the new default tree.
        for tag, version in [('base', '36.0.0'), ('extra', '35.0.0')]:
            with tarfile.open(self.root / f'{tag}.tar.xz', 'w:xz') as tar:
                if tag == 'base':
                    for directory in ('platforms', 'platform-tools', 'cmdline-tools', 'licenses'):
                        tar.add(self.sdk / directory, arcname=f'android-sdk/{directory}')
                tar.add(self.sdk / f'build-tools/{version}', arcname=f'android-sdk/build-tools/{version}')
        config = {'target': 'aarch64-linux-android', 'baseRelease': 'base',
                  'additionalBuildTools': [{'release': 'extra', 'version': '35.0.0'}],
                  'requiredPlatforms': [35, 36], 'requiredBuildTools': ['35.0.0', '36.0.0']}
        import shutil
        def api(*args):
            tag = args[-1].split('/')[-1]
            return json.dumps({'assets': [{'name': 'android-sdk-aarch64-linux-android.tar.xz',
                'digest': 'sha256:' + hashlib.sha256((self.root / f'{tag}.tar.xz').read_bytes()).hexdigest()}]})
        def download(args, **kwargs):
            directory = Path(args[args.index('--dir') + 1])
            shutil.copyfile(self.root / f'{args[3]}.tar.xz', directory / 'android-sdk-aarch64-linux-android.tar.xz')
        with patch.object(assembler, 'run', side_effect=api), patch.object(assembler.subprocess, 'run', side_effect=download):
            sdk = assembler.assemble(config, 'example/sdk', self.root / 'work')
            self.assertTrue((sdk / 'build-tools/35.0.0/package.xml').exists())
            self.assertTrue((sdk / 'build-tools/36.0.0/package.xml').exists())
            self.assertTrue((sdk / 'platforms/android-36/android.jar').exists())
            self.assertEqual(len(json.loads((self.root / 'work/sources.json').read_text())), 2)
        def wrong_digest(*args):
            return json.dumps({'assets': [{'name': 'android-sdk-aarch64-linux-android.tar.xz',
                                          'digest': 'sha256:' + '0' * 64}]})
        with patch.object(assembler, 'run', side_effect=wrong_digest), patch.object(assembler.subprocess, 'run', side_effect=download):
            with self.assertRaisesRegex(ValueError, 'SHA-256 mismatch'):
                assembler.assemble(config, 'example/sdk', self.root / 'bad')

    def test_archive_extraction_rejects_path_escape(self):
        archive = self.root / 'unsafe.tar'
        with tarfile.open(archive, 'w') as tar:
            tar.addfile(tarfile.TarInfo('../../escape'))
        with self.assertRaises(tarfile.FilterError):
            assembler.extract(archive, self.root / 'safe')
        self.assertFalse((self.root / 'escape').exists())


if __name__ == '__main__':
    unittest.main()
