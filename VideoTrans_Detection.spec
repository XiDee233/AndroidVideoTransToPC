# -*- mode: python ; coding: utf-8 -*-


a = Analysis(
    ['gui_main.py'],
    pathex=[],
    binaries=[],
    datas=[('yolo11n.pt', '.'), ('best.pt', '.'), ('best.onnx', '.'), ('ultralytics', 'ultralytics')],
    hiddenimports=['ultralytics', 'ultralytics.models', 'ultralytics.models.yolo', 'ultralytics.engine', 'ultralytics.utils', 'ultralytics.nn.FRFN', 'ultralytics.nn.SEAM', 'cv2', 'numpy', 'torch', 'torchvision', 'PIL', 'flask', 'requests', 'matplotlib', 'matplotlib.pyplot', 'matplotlib.backends', 'matplotlib.backends.backend_agg', 'scipy', 'scipy.optimize', 'scipy.optimize.linear_sum_assignment'],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['pandas', 'jupyter', 'IPython'],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='VideoTrans_Detection',
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
