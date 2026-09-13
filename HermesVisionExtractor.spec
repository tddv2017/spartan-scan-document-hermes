# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.utils.hooks import collect_all

datas = []
binaries = []
hiddenimports = ['pydantic', 'pypdf', 'PIL', 'win32gui', 'win32con', 'win32api']
tmp_ret = collect_all('rapidocr_onnxruntime')
datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]
tmp_ret = collect_all('reportlab')
datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]


a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        'torch', 'torchvision', 'torchaudio',
        'matplotlib', 'scipy', 'pandas',
        'IPython', 'jupyter', 'notebook',
        'pytest', 'unittest',
        'cryptography', 'Pythonwin',
    ],
    noarchive=False,
    optimize=0,
)

# Strip unnecessary heavy DLLs (video/directml/crypto) to keep single-file EXE under 100MB for GitHub
excluded_binary_keywords = ['ffmpeg', 'directml', 'mfc140', '_avif', 'cryptography', 'libcrypto', 'pythonwin']
a.binaries = [x for x in a.binaries if not any(kw in x[0].lower() for kw in excluded_binary_keywords)]

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='HermesVisionExtractor',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
