"""Keeps the Mac and Windows folders in step.

Each folder holds a complete JARVIS, so either can be downloaded and run on its own. Most of the
code is the same in both: every file that exists in both folders must be identical. Only the
platform's own files (mac.py, windows.py, the launchers, setup scripts, requirements and
"START HERE" notes) differ, and those exist in one folder only. The ui folder (the setup window
and the hub) is shared like the rest.

After changing a shared file in one folder, copy it to the other:
    python sync_folders.py Mac        # Mac -> Windows
    python sync_folders.py Windows    # Windows -> Mac
To check that they match (CI runs this):
    python sync_folders.py --check
"""
import filecmp
import os
import shutil
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
FOLDERS = ('Mac', 'Windows')
SKIP = {'__pycache__', '.venv', 'models'}
PAGES = 'ui'  # the setup window and the hub: shared too


def files(folder):
    """The files JARVIS is made of in one folder (not what it writes while running)."""
    root = os.path.join(HERE, folder)
    found = {name for name in os.listdir(root)
             if name not in SKIP and os.path.isfile(os.path.join(root, name))
             and name.endswith(('.py', '.txt', '.sh', '.ps1', '.bat', '.command'))}
    pages = os.path.join(root, PAGES)
    if os.path.isdir(pages):
        found |= {f'{PAGES}/{name}' for name in os.listdir(pages) if os.path.isfile(os.path.join(pages, name))}
    return found


def shared():
    return sorted(files('Mac') & files('Windows'))


def different():
    return [name for name in shared()
            if not filecmp.cmp(os.path.join(HERE, 'Mac', name), os.path.join(HERE, 'Windows', name), shallow=False)]


def main(args):
    if args == ['--check']:
        bad = different()
        if bad:
            print('These files differ between Mac and Windows; copy the newer one across with\n'
                  '"python sync_folders.py Mac" or "python sync_folders.py Windows":')
            for name in bad:
                print('  ' + name)
            return 1
        print(f'Mac and Windows share {len(shared())} identical files.')
        return 0
    if len(args) == 1 and args[0] in FOLDERS:
        source = args[0]
        target = FOLDERS[1 - FOLDERS.index(source)]
        changed = different()
        for name in changed:
            shutil.copy2(os.path.join(HERE, source, name), os.path.join(HERE, target, name))
            print(f'Copied {name} from {source} to {target}.')
        if not changed:
            print('Nothing to copy: the shared files already match.')
        return 0
    print(__doc__)
    return 2


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
