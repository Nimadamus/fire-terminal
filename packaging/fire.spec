# PyInstaller spec for FIRE.
#
# Packaging rule, and the reason this file is explicit rather than generated:
# assume anything inside the bundle can be extracted and read. So the bundle
# must contain only what the customer application needs. There is no
# obfuscation step here on purpose, because relying on one would be a false
# sense of safety.
#
# Build:  pyinstaller packaging/fire.spec --noconfirm
#
# `packaging/verify_bundle.py` runs after the build and fails the release if
# anything private, credential shaped or oversized made it in.

import os
import sys

# SPECPATH, not a relative path: PyInstaller is invoked from the repository
# root, so os.path.abspath('../src') would resolve outside the project.
sys.path.insert(0, os.path.join(SPECPATH, '..', 'src'))
from fire.version import VERSION            # noqa: E402

block_cipher = None

# Windows version resource, generated here so it can never drift from
# fire/version.py. Without it, right clicking FIRE.exe and opening Properties
# shows an empty Details tab, which reads as unfinished software, and signing
# tools have nothing to attach a publisher name to.
_parts = tuple(int(x) for x in VERSION.split('-')[0].split('.')) + (0, 0, 0, 0)
_quad = _parts[:4]

VERSION_RESOURCE = f"""
VSVersionInfo(
  ffi=FixedFileInfo(filevers={_quad}, prodvers={_quad},
                    mask=0x3f, flags=0x0, OS=0x40004, fileType=0x1,
                    subtype=0x0, date=(0, 0)),
  kids=[
    StringFileInfo([
      StringTable('040904B0', [
        StringStruct('CompanyName', 'FIRE'),
        StringStruct('FileDescription', 'FIRE execution terminal'),
        StringStruct('FileVersion', '{VERSION}'),
        StringStruct('InternalName', 'FIRE'),
        StringStruct('OriginalFilename', 'FIRE.exe'),
        StringStruct('ProductName', 'FIRE'),
        StringStruct('ProductVersion', '{VERSION}'),
      ])
    ]),
    VarFileInfo([VarStruct('Translation', [1033, 1200])])
  ]
)
"""

_version_path = os.path.join(SPECPATH, 'fire_version_info.txt')
with open(_version_path, 'w', encoding='utf-8') as fh:
    fh.write(VERSION_RESOURCE)

a = Analysis(
    ['../src/fire/__main__.py'],
    pathex=['../src'],
    binaries=[],
    # Customer facing guidance travels with the application. Someone
    # whose laptop was stolen should not have to find a web page.
    datas=[('fire.ico', '.'),
           ('../docs/CREDENTIALS.md', 'docs'),
           ('../docs/TROUBLESHOOTING.md', 'docs'),
           ('../docs/LICENSE.txt', 'docs')],
    hiddenimports=[
        'fire.venues.demo.venue',
        'fire.venues.kalshi.venue',
        'fire.ui.main_window',
        'fire.ui.onboarding',
        'fire.ui.preferences_window',
        'fire.ui.diagnostics_window',
    ],
    hookspath=[],
    runtime_hooks=[],
    # Keep the bundle small and the surface honest. None of these are used by
    # the customer application.
    excludes=[
        'numpy', 'pandas', 'scipy', 'matplotlib', 'IPython', 'jupyter',
        'notebook', 'pytest', 'setuptools', 'pip', 'sqlite3', 'test',
        'unittest', 'pydoc_data', 'lib2to3', 'distutils',
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='FIRE',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,          # windowed app, no console flash
    disable_windowed_traceback=True,   # a customer never sees a traceback
    icon='fire.ico',
    version=_version_path,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name='FIRE',
)
