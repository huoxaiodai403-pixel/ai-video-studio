"""Clean-package rendering sources and consent boundaries for friend installs."""
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import unittest
from unittest.mock import patch
import zipfile

import testing_support as tempfile
import jianying_bridge
import simon_source

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('studio_release_builder', ROOT/'packaging/build_release.py')
release = importlib.util.module_from_spec(spec)
spec.loader.exec_module(release)


class BundleTests(unittest.TestCase):
    def test_source_zip_extracts_with_patched_runtime_fonts_and_stickers_without_git(self):
        files = release.sources()
        names = {path.relative_to(ROOT).as_posix() for path in files}
        for name in simon_source.FILES:
            self.assertIn('apps/simon-skills/' + name, names)
        self.assertFalse(any(set(Path(name).parts) & {'node_modules', '.git', '.venv', 'projects', 'cache'}
                             for name in names))
        with tempfile.TemporaryDirectory() as folder:
            dest = Path(folder)
            entries = {'studio/' + path.relative_to(ROOT).as_posix(): path.read_bytes()
                       for path in simon_source.validate_bundle()}
            entries['studio/workflows/simon-windows.patch'] = (ROOT/'workflows/simon-windows.patch').read_bytes()
            archive = dest/'source.zip'
            release.archive(archive, entries, '0.2.1')
            with zipfile.ZipFile(archive) as zipped:
                zipped.extractall(dest)
            self.assertEqual(len(simon_source.validate_bundle(dest/'studio')), 16)
            renderer = dest/'studio/apps/simon-skills/skills/whiteboard-video/lib/render.js'
            renderer.write_bytes(renderer.read_bytes() + b'\n// unexpected edit\n')
            with self.assertRaisesRegex(ValueError, 'checksum mismatch'):
                release.sources(dest/'studio')
            renderer.unlink()
            with self.assertRaises(OSError):
                release.sources(dest/'studio')

    def test_missing_bundle_blocks_release_instead_of_creating_incomplete_zip(self):
        with tempfile.TemporaryDirectory() as folder:
            with self.assertRaises(OSError):
                release.sources(Path(folder))


class SetupTests(unittest.TestCase):
    @unittest.skipUnless(shutil.which('powershell.exe'), 'Windows PowerShell required')
    def test_duplicate_path_aliases_preserve_entries_and_allow_child_launch(self):
        import ctypes
        from ctypes import wintypes as w
        # Python's subprocess env= normalizes duplicate Windows names itself.
        # Use a raw Windows environment block to reproduce the inherited defect.
        class StartupInfo(ctypes.Structure):
            _fields_ = [('cb', w.DWORD), ('reserved', w.LPWSTR), ('desktop', w.LPWSTR), ('title', w.LPWSTR),
                        ('x', w.DWORD), ('y', w.DWORD), ('xs', w.DWORD), ('ys', w.DWORD),
                        ('xc', w.DWORD), ('yc', w.DWORD), ('attr', w.DWORD), ('flags', w.DWORD),
                        ('show', w.WORD), ('size', w.WORD), ('reserved2', ctypes.c_void_p),
                        ('stdin', w.HANDLE), ('stdout', w.HANDLE), ('stderr', w.HANDLE)]
        class ProcessInfo(ctypes.Structure):
            _fields_ = [('process', w.HANDLE), ('thread', w.HANDLE), ('pid', w.DWORD), ('tid', w.DWORD)]
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            shutil.copyfile(ROOT/'scripts/Initialize-StudioEnvironment.ps1', root/'Initialize-StudioEnvironment.ps1')
            probe = root/'probe.ps1'
            probe.write_text('''$ErrorActionPreference = 'Stop'
$before = @([Environment]::GetEnvironmentVariables('Process').Keys | Where-Object { $_ -ieq 'Path' })
if ($before.Count -ne 3) { throw 'Test did not inherit all three Path aliases.' }
. (Join-Path $PSScriptRoot 'Initialize-StudioEnvironment.ps1')
$aliases = @([Environment]::GetEnvironmentVariables('Process').Keys | Where-Object { $_ -ieq 'Path' })
if ($aliases.Count -ne 1 -or $env:Path -notlike '*studio-path-one*' -or $env:Path -notlike '*studio-path-two*') { throw 'Path entries were lost or duplicated.' }
$child = Start-Process -FilePath $env:COMSPEC -ArgumentList @('/d', '/c', 'exit 0') -WindowStyle Hidden -Wait -PassThru
exit $child.ExitCode
''', encoding='utf-8')
            env = {key: value for key, value in os.environ.items() if key.lower() != 'path'}
            env.update(Path=os.environ.get('PATH', ''), path='C:\\studio-path-one', PATH='C:\\studio-path-two')
            block = ctypes.create_unicode_buffer('\0'.join(f'{key}={value}' for key, value in sorted(env.items())) + '\0\0')
            command = ctypes.create_unicode_buffer(subprocess.list2cmdline([
                shutil.which('powershell.exe'), '-NoProfile', '-NonInteractive', '-ExecutionPolicy', 'Bypass', '-File', str(probe)]))
            startup, process = StartupInfo(), ProcessInfo()
            startup.cb = ctypes.sizeof(startup)
            kernel = ctypes.WinDLL('kernel32', use_last_error=True)
            create = kernel.CreateProcessW
            create.argtypes = [w.LPCWSTR, w.LPWSTR, ctypes.c_void_p, ctypes.c_void_p, w.BOOL, w.DWORD,
                               ctypes.c_void_p, w.LPCWSTR, ctypes.POINTER(StartupInfo), ctypes.POINTER(ProcessInfo)]
            create.restype = w.BOOL
            kernel.WaitForSingleObject.argtypes = [w.HANDLE, w.DWORD]
            kernel.GetExitCodeProcess.argtypes = [w.HANDLE, ctypes.POINTER(w.DWORD)]
            kernel.CloseHandle.argtypes = [w.HANDLE]
            kernel.TerminateProcess.argtypes = [w.HANDLE, w.UINT]
            self.assertTrue(create(None, command, None, None, False, 0x08000400, block, None,
                                   ctypes.byref(startup), ctypes.byref(process)))
            try:
                waited = kernel.WaitForSingleObject(process.process, 15000)
                if waited != 0:
                    kernel.TerminateProcess(process.process, 1)
                    kernel.WaitForSingleObject(process.process, 5000)
                self.assertEqual(waited, 0, 'PowerShell launch check timed out')
                code = w.DWORD()
                self.assertTrue(kernel.GetExitCodeProcess(process.process, ctypes.byref(code)))
                self.assertEqual(code.value, 0)
            finally:
                kernel.CloseHandle(process.thread)
                kernel.CloseHandle(process.process)

    def test_setup_distinguishes_consent_bridge_and_first_launch(self):
        cases = [(False, False, None, 'ask_install'), (True, False, None, 'install_bridge'),
                 (True, True, None, 'first_launch'), (True, True, 'drafts', 'ready'),
                 (False, True, 'drafts', 'ask_install')]
        for installed, bridge, drafts, expected in cases:
            with self.subTest(expected=expected), patch.object(jianying_bridge, 'discover', return_value={
                    'installed': installed, 'bridge_ready': bridge, 'draft_root': drafts}):
                status = jianying_bridge.status()
                self.assertEqual(status['setup']['action'], expected)
                self.assertEqual(status['setup']['requires_install_consent'], not installed)
                self.assertEqual(status['editable_available'], expected == 'ready')

    @unittest.skipUnless(shutil.which('powershell.exe'), 'Windows PowerShell required')
    def test_noninteractive_missing_app_does_not_install_without_consent(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            scripts = root/'scripts'
            scripts.mkdir()
            for name in ('Install-JianyingBridge.ps1', 'Initialize-StudioEnvironment.ps1'):
                shutil.copyfile(ROOT/'scripts'/name, scripts/name)
            (scripts/'jianying_bridge.py').write_text('print(\'{"installed":false}\')', encoding='utf-8')
            result = subprocess.run(['powershell.exe', '-NoProfile', '-NonInteractive',
                                     '-ExecutionPolicy', 'Bypass', '-File', str(scripts/'Install-JianyingBridge.ps1'),
                                     '-PythonPath', sys.executable, '-NonInteractive'], capture_output=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn(b'Ask the user first', result.stdout + result.stderr)
            self.assertFalse((root/'apps').exists())


if __name__ == '__main__':
    unittest.main()
