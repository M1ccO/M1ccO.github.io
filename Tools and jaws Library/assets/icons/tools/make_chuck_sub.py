"""
Fix jaw_main.png: remove near-white background -> transparent.
Also create jaw_sub.png as the horizontally mirrored version.

Run from any working directory - paths are resolved relative to this script.
"""
from pathlib import Path
import numpy as np
from PySide6.QtGui import QImage, QTransform
from PySide6.QtWidgets import QApplication
import sys

app = QApplication.instance() or QApplication(sys.argv)

BASE = Path(__file__).resolve().parent
SRC_ORIGINAL = BASE / "jaw_main.png"

if not SRC_ORIGINAL.exists():
    print(f"Source image not found: {SRC_ORIGINAL}")
    raise SystemExit(1)

# --- Load and make transparent ---
img = QImage(str(SRC_ORIGINAL))
if img.isNull():
    print("Failed to load image.")
    raise SystemExit(2)

img = img.convertToFormat(QImage.Format_ARGB32)
w, h = img.width(), img.height()

# numpy array layout for Format_ARGB32 on little-endian: [B, G, R, A]
arr = np.frombuffer(img.constBits(), dtype=np.uint8).copy().reshape((h, w, 4))

# Remove near-white background: all three channels above threshold
# Format_ARGB32 on little-endian: arr[..., 0]=B, arr[..., 1]=G, arr[..., 2]=R, arr[..., 3]=A
BG_THRESHOLD = 235
near_white = (arr[:, :, 0] > BG_THRESHOLD) & (arr[:, :, 1] > BG_THRESHOLD) & (arr[:, :, 2] > BG_THRESHOLD)
arr[near_white, 3] = 0  # set alpha to 0

fixed_img = QImage(arr.tobytes(), w, h, w * 4, QImage.Format_ARGB32)

# --- Save jaw_main.png (fixed, transparent) ---
ok = fixed_img.save(str(SRC_ORIGINAL))
if not ok:
    print(f"Failed to save fixed jaw_main.png")
    raise SystemExit(3)
print(f"Fixed and saved: {SRC_ORIGINAL}")

# --- Create jaw_sub.png: horizontal mirror of the fixed image ---
mirrored_img = fixed_img.transformed(QTransform().scale(-1, 1))
DST = BASE / "jaw_sub.png"
ok = mirrored_img.save(str(DST))
if not ok:
    print(f"Failed to save jaw_sub.png")
    raise SystemExit(4)
print(f"Saved mirrored: {DST}")
