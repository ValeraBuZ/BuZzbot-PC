import subprocess
import sys
from pathlib import Path
import shutil

ROOT = Path(__file__).resolve().parent

if __name__ == '__main__':
    command = [sys.executable, '-m', 'PyInstaller', '--noconfirm', '--onefile', '--windowed',
               '--name', 'DoomsdayGearValue', '--paths', str(ROOT.parent),
               '--distpath', str(ROOT / 'dist' / 'DoomsdayGearValue'),
               '--workpath', str(ROOT / 'build'), '--specpath', str(ROOT)]
    # Namespace projections load native WinRT modules dynamically.
    for module in ['winrt.runtime', 'winrt.windows.foundation', 'winrt.windows.foundation.collections',
                   'winrt.windows.globalization', 'winrt.windows.media.ocr', 'winrt.windows.storage',
                   'winrt.windows.storage.streams', 'winrt.windows.graphics.imaging']:
        command.extend(['--collect-all', module])
    for asset in ['web', 'evidence', 'seed.json', 'research.json']:
        dest = f'gear_value/{asset}' if (ROOT / asset).is_dir() else 'gear_value'
        command.extend(['--add-data', f'{ROOT / asset};{dest}'])
    command.append(str(ROOT / 'launcher.py'))
    subprocess.run(command, cwd=ROOT.parent, check=True)
    for document in ['README.md', 'QUICKSTART.txt']:
        shutil.copy2(ROOT / document, ROOT / 'dist' / 'DoomsdayGearValue' / document)
