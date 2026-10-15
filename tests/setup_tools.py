import importlib.util
import hashlib
import os
from pathlib import Path
import subprocess
import tarfile
import tempfile
import unittest

SCRIPTS = Path(__file__).resolve().parents[1] / 'scripts'


def load(name):
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / (name + '.py'))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


bootstrap = load('bootstrap_toolchain')
check_pen = load('check_pen')


class SetupChecks(unittest.TestCase):
    def test_corrupted_package_is_rejected_before_extraction(self):
        with tempfile.TemporaryDirectory() as temporary:
            cache = Path(temporary)
            (cache / 'package.deb').write_bytes(b'broken archive')
            with self.assertRaisesRegex(ValueError, 'checksum mismatch'):
                bootstrap.download({'file': 'package.deb', 'sha256': '0' * 64}, cache, offline=True)

    def test_existing_directory_is_never_replaced(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            keep = root / 'my-toolchain'
            keep.mkdir()
            (keep / 'important').write_text('keep')
            with self.assertRaises(FileExistsError):
                bootstrap.bootstrap(keep, root / 'cache')
            self.assertEqual((keep / 'important').read_text(), 'keep')

    def test_unsupported_or_modified_pen_is_not_approved_for_fresh_install(self):
        output = 'uid=0\narchitecture=aarch64\noem_available_kib=65536\nuserdata_available_kib=1048576\n'
        self.assertFalse(check_pen.assess(output + 'application=unknown\n')['fresh_install_checks_passed'])
        modified = check_pen.assess(output + f'application=modified\noriginal_backup={check_pen.EXPECTED}\n')
        self.assertFalse(modified['fresh_install_checks_passed'])
        self.assertTrue(modified['warnings'])
        fresh = check_pen.assess(output + f'application={check_pen.EXPECTED}\n')
        self.assertTrue(fresh['fresh_install_checks_passed'])
        self.assertFalse(check_pen.assess(output.replace('uid=0', 'uid=1000') + f'application={check_pen.EXPECTED}\n')['fresh_install_checks_passed'])
        self.assertFalse(check_pen.assess(output.replace('1048576', '0') + f'application={check_pen.EXPECTED}\n')['fresh_install_checks_passed'])


class PenInstaller(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        root = Path(self.temporary.name)
        self.pen = root / 'pen'
        self.stage = root / 'stage'
        self.stage.mkdir()
        (self.pen / 'oem').mkdir(parents=True)
        (self.pen / 'userdata/translatepen').mkdir(parents=True)
        (self.pen / 'usr/qml/TranslatePen').mkdir(parents=True)
        (self.pen / '.translatepen-test-root').touch()
        self.original = b'test original firmware'
        (self.pen / 'oem/scanpen').write_bytes(self.original)
        (self.pen / 'userdata/translatepen/migaku.json').write_text('{"token":"private-fixture"}')
        for name in ['app/Japanese.qml', 'Native/libtranslatepennative.so', 'Native/qmldir',
                     'dictionary.sqlite', 'deinflect.json', 'scanpen', 'ocr.json', 'restore_pen.sh']:
            path = self.stage / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(('fixture ' + name).encode())
        sums = ''.join(f'{hashlib.sha256(p.read_bytes()).hexdigest()}  {p.relative_to(self.stage)}\n'
                       for p in self.stage.rglob('*') if p.is_file())
        (self.stage / 'SHA256SUMS').write_text(sums)

    def install(self, extra_env=None):
        env = {**os.environ, 'TRANSLATEPEN_TEST_ROOT': str(self.pen),
               'TRANSLATEPEN_TEST_EXPECTED': hashlib.sha256(self.original).hexdigest(), **(extra_env or {})}
        return subprocess.run(['sh', str(SCRIPTS / 'install_pen.sh')], cwd=self.stage,
                              env=env, capture_output=True, text=True, timeout=15)

    def test_install_preserves_original_and_existing_credentials(self):
        result = self.install()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual((self.pen / 'oem/scanpen').read_bytes(), (self.stage / 'scanpen').read_bytes())
        base = self.pen / 'userdata/translatepen'
        self.assertEqual((base / 'backups/scanpen.original').read_bytes(), self.original)
        self.assertEqual((base / 'migaku.json').read_text(), '{"token":"private-fixture"}')
        backup = next((base / 'backups').glob('install-*/files.tar'))
        with tarfile.open(backup) as archive:
            self.assertEqual(archive.extractfile('oem/scanpen').read(), self.original)
        self.assertEqual(backup.stat().st_mode & 0o777, 0o600)
        self.assertEqual((base / 'ocr.json').stat().st_mode & 0o777, 0o600)

    def test_corrupt_payload_does_not_change_firmware(self):
        (self.stage / 'Native/libtranslatepennative.so').write_bytes(b'corrupted')
        self.assertNotEqual(self.install().returncode, 0)
        self.assertEqual((self.pen / 'oem/scanpen').read_bytes(), self.original)
        self.assertFalse((self.pen / 'userdata/translatepen/backups').exists())

    def test_restore_and_reinstall_in_offline_filesystem_fixture(self):
        self.assertEqual(self.install().returncode, 0)
        env = {**os.environ, 'TRANSLATEPEN_TEST_ROOT': str(self.pen),
               'TRANSLATEPEN_TEST_EXPECTED': hashlib.sha256(self.original).hexdigest()}
        result = subprocess.run(['sh', str(SCRIPTS / 'restore_pen.sh')], env=env,
                                capture_output=True, text=True, timeout=15)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual((self.pen / 'oem/scanpen').read_bytes(), self.original)
        self.assertEqual(self.install().returncode, 0)
        self.assertEqual((self.pen / 'oem/scanpen').read_bytes(), (self.stage / 'scanpen').read_bytes())

    def test_restore_refuses_corrupted_backup(self):
        self.assertEqual(self.install().returncode, 0)
        (self.pen / 'userdata/translatepen/backups/scanpen.original').write_bytes(b'broken')
        env = {**os.environ, 'TRANSLATEPEN_TEST_ROOT': str(self.pen),
               'TRANSLATEPEN_TEST_EXPECTED': hashlib.sha256(self.original).hexdigest()}
        result = subprocess.run(['sh', str(SCRIPTS / 'restore_pen.sh')], env=env,
                                capture_output=True, text=True, timeout=15)
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual((self.pen / 'oem/scanpen').read_bytes(), (self.stage / 'scanpen').read_bytes())

    def test_modified_firmware_is_refused(self):
        (self.pen / 'oem/scanpen').write_bytes(b'unknown firmware')
        result = self.install()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('Restore stock first', result.stderr)

    def test_insufficient_space_stops_before_backups_or_replacement(self):
        fake = Path(self.temporary.name) / 'commands'
        fake.mkdir()
        (fake / 'df').write_text('#!/bin/sh\nprintf "Filesystem 1024-blocks Used Available Capacity Mounted\\nfixture 100 100 0 100%% /\\n"\n')
        (fake / 'df').chmod(0o755)
        result = self.install({'PATH': str(fake) + os.pathsep + os.environ['PATH']})
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('Insufficient /userdata', result.stderr)
        self.assertEqual((self.pen / 'oem/scanpen').read_bytes(), self.original)


if __name__ == '__main__':
    unittest.main()
