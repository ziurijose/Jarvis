"""Runs the same checks as CI (.github/workflows/main.yml) on this computer:

    python check.py

The Mac and Windows folders match, every Python file compiles, flake8 finds no undefined names
or unused imports, and the unit tests pass. The tests run once, in the Windows folder: the test
files and the code they test are shared, so the Mac copies are the same files.
Exits non-zero if anything fails.
"""
import glob
import os
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))


def python_for(folder):
    """The folder's own .venv Python when it has one (its packages are installed there)."""
    for path in ('.venv/Scripts/python.exe', '.venv/bin/python'):
        candidate = os.path.join(HERE, folder, path)
        if os.path.exists(candidate):
            return candidate
    return sys.executable


def flake8_command():
    try:
        import flake8  # noqa: F401
        return [sys.executable, '-m', 'flake8']
    except ImportError:
        pass
    if shutil.which('uvx'):
        return ['uvx', 'flake8']
    return None


def run(name, command, cwd):
    print(f'--- {name}', flush=True)
    result = subprocess.run(command, cwd=cwd)
    print(f"{'ok' if result.returncode == 0 else 'FAILED'}: {name}\n", flush=True)
    return result.returncode == 0


def main():
    results = [run('Mac and Windows folders match', [sys.executable, 'sync_folders.py', '--check'], HERE)]
    lint = flake8_command()
    for folder in ('Windows', 'Mac'):
        cwd = os.path.join(HERE, folder)
        files = sorted(os.path.basename(f) for f in glob.glob(os.path.join(cwd, '*.py')))
        results.append(run(f'{folder}: compile', [sys.executable, '-m', 'py_compile'] + files, cwd))
        if lint:
            results.append(run(f'{folder}: flake8', lint + ['--select=F'] + files, cwd))
        else:
            print(f'--- {folder}: flake8 skipped (install flake8 or uv to run it)\n')
    results.append(run('Windows: unit tests', [python_for('Windows'), '-m', 'unittest'],
                       os.path.join(HERE, 'Windows')))
    passed = all(results)
    print('ALL CHECKS PASSED' if passed else 'SOME CHECKS FAILED')
    return 0 if passed else 1


if __name__ == '__main__':
    sys.exit(main())
