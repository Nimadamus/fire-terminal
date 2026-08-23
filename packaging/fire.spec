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

block_cipher = None

a = Analysis(
    ['../src/fire/__main__.py'],
    pathex=['../src'],
    binaries=[],
    # Customer facing guidance travels with the application. Someone
    # whose laptop was stolen should not have to find a web page.
    datas=[('../docs/CREDENTIALS.md', 'docs'),
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
    icon=None,
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
