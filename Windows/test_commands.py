"""Tests for run_command: commands run at once, deletes and overwrites wait for a spoken yes,
and talking stops a running command. Run with:  python -m unittest test_commands"""
import os
import tempfile
import threading
import time
import unittest

import commands

IS_WINDOWS = os.name == 'nt'


def delete(path):
    return f'Remove-Item "{path}"' if IS_WINDOWS else f'rm "{path}"'


class RunTest(unittest.TestCase):
    def test_a_harmless_command_runs_straight_away(self):
        self.assertIn('hello', commands.run_command('echo hello'))

    def test_the_output_says_when_a_command_failed(self):
        result = commands.run_command('exit 3')
        self.assertIn('exit code 3', result)

    def test_talking_stops_a_long_command(self):
        interrupted = threading.Event()
        threading.Timer(0.3, interrupted.set).start()
        started = time.monotonic()
        result = commands.run_command('Start-Sleep 600' if IS_WINDOWS else 'sleep 600',
                                      interrupted=interrupted)
        self.assertLess(time.monotonic() - started, 10)
        self.assertIn('Stopped', result)


class ConfirmTest(unittest.TestCase):
    def setUp(self):
        commands._read_back.clear()
        handle, self.path = tempfile.mkstemp()
        os.close(handle)
        self.addCleanup(lambda: os.path.exists(self.path) and os.remove(self.path))

    def test_a_delete_waits_for_a_spoken_yes(self):
        command = delete(self.path)
        first = commands.run_command(command, heard='delete that file')
        self.assertIn('Not run yet', first)
        self.assertTrue(os.path.exists(self.path))
        commands.run_command(command, confirmed=True, heard='yes, do it')
        self.assertFalse(os.path.exists(self.path))

    def test_confirmed_without_reading_it_back_first_does_not_run(self):
        commands.run_command(delete(self.path), confirmed=True, heard='yes')
        self.assertTrue(os.path.exists(self.path))

    def test_a_no_does_not_run(self):
        command = delete(self.path)
        commands.run_command(command, heard='delete that file')
        commands.run_command(command, confirmed=True, heard="no, don't")
        self.assertTrue(os.path.exists(self.path))


class RiskyTest(unittest.TestCase):
    def test_deletes_and_overwrites_are_risky(self):
        for command in ('Remove-Item C:\\x', 'rm -rf ~/x', 'del x.txt', 'rmdir old', 'rd /s old',
                        'Get-ChildItem | ri', 'echo hi > notes.txt', 'Set-Content a.txt b',
                        'Out-File a.txt', 'Clear-Content a.txt', 'Move-Item a b -Force',
                        'Format-Volume D', 'Clear-RecycleBin', 'Copy-Item a b -Force'):
            self.assertTrue(commands.is_risky(command), command)

    def test_everyday_commands_are_not(self):
        for command in ('Get-Process', 'echo hello', 'Start-Process notepad', 'dir C:\\Users',
                        'Get-ChildItem -Recurse | Measure-Object', 'ipconfig', 'echo hi >> log.txt',
                        'git status', 'New-Item -ItemType Directory projects'):
            self.assertFalse(commands.is_risky(command), command)


if __name__ == '__main__':
    unittest.main()
