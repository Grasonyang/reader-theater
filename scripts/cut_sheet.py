# /// script
# requires-python = ">=3.11"
# dependencies = ["pillow", "numpy"]
# ///
"""把綠幕角色表切成一人一張去背 PNG。

用法：
    uv run scripts/cut_sheet.py <角色表圖> <輸出資料夾> <角色 id 依序...> [--cols 2]

角色表是 2x2（或 --cols 指定欄數）的格子，每格一個角色，背景是綠色。
去背用色相判斷（綠色且飽和度夠高），邊緣做一點羽化；輸出依內容裁邊，
下方不裁（角色通常被畫面下緣切掉，保留到格子底部）。
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageFilter

# 綠色的色相範圍（0-360）與最低飽和度、明度
HUE_LO, HUE_HI = 70, 170
SAT_MIN, VAL_MIN = 0.30, 0.15
FEATHER_PX = 1.5
TRIM_MARGIN = 8
# 格子之間常有白色分隔線，先往內縮這麼多像素再去背
CELL_INSET = 10
# 角色被格子邊緣切到（頭髮、手臂超出格子）時，那一側用這麼寬的漸層淡出，
# 疊在別的角色前面才不會出現一條直直的切邊
EDGE_FEATHER_PX = 56
EDGE_TOUCH_RATIO = 0.08


def green_mask(rgb: np.ndarray) -> np.ndarray:
    """回傳每個像素是否為背景綠（True = 背景）。"""
    hsv = np.asarray(Image.fromarray(rgb).convert("HSV"), dtype=np.float32)
    hue = hsv[..., 0] * 360 / 255
    sat = hsv[..., 1] / 255
    val = hsv[..., 2] / 255
    return (hue >= HUE_LO) & (hue <= HUE_HI) & (sat >= SAT_MIN) & (val >= VAL_MIN)


def despill(rgb: np.ndarray, alpha: np.ndarray) -> np.ndarray:
    """邊緣的綠色溢色：把綠通道壓到不超過紅藍的平均。"""
    out = rgb.astype(np.float32)
    edge = (alpha > 0) & (alpha < 255)
    limit = (out[..., 0] + out[..., 2]) / 2
    g = out[..., 1]
    out[..., 1] = np.where(edge & (g > limit), limit, g)
    return out.clip(0, 255).astype(np.uint8)


def cut(cell: Image.Image) -> Image.Image:
    rgb = np.asarray(cell.convert("RGB"))
    bg = green_mask(rgb)
    alpha = Image.fromarray(((~bg) * 255).astype(np.uint8))
    # 去掉背景裡的零星小點、填掉角色裡誤判的小洞，再羽化邊緣
    alpha = alpha.filter(ImageFilter.MinFilter(3)).filter(ImageFilter.MaxFilter(3))
    alpha = alpha.filter(ImageFilter.GaussianBlur(FEATHER_PX))
    a = np.asarray(alpha)
    rgba = np.dstack([despill(rgb, a), a])
    img = Image.fromarray(rgba, "RGBA")
    # 依內容裁邊：左右上留邊，下緣保留到底
    ys, xs = np.where(a > 16)
    if len(xs) == 0:
        return img
    x0, x1 = max(0, xs.min() - TRIM_MARGIN), min(img.width, xs.max() + TRIM_MARGIN)
    y0 = max(0, ys.min() - TRIM_MARGIN)
    return feather_cut_edges(img.crop((x0, y0, x1, img.height)))


def feather_cut_edges(img: Image.Image) -> Image.Image:
    """左、右、上三側若有內容貼到邊（被格子切掉），該側做漸層淡出。"""
    rgba = np.asarray(img).copy()
    a = rgba[..., 3].astype(np.float32)
    n = EDGE_FEATHER_PX
    ramp = np.linspace(0.0, 1.0, n, dtype=np.float32)

    def touches(strip):
        return (strip > 16).mean() > EDGE_TOUCH_RATIO

    if touches(a[:, :3]):
        a[:, :n] *= ramp[None, :]
    if touches(a[:, -3:]):
        a[:, -n:] *= ramp[::-1][None, :]
    if touches(a[:3, :]):
        a[:n, :] *= ramp[:, None]
    rgba[..., 3] = a.clip(0, 255).astype(np.uint8)
    return Image.fromarray(rgba, "RGBA")


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("sheet", type=Path)
    parser.add_argument("out", type=Path)
    parser.add_argument("ids", nargs="+", help="角色 id，照格子由左到右、由上到下")
    parser.add_argument("--cols", type=int, default=2)
    args = parser.parse_args()

    sheet = Image.open(args.sheet).convert("RGB")
    rows = -(-len(args.ids) // args.cols)
    cw, ch = sheet.width // args.cols, sheet.height // rows
    args.out.mkdir(parents=True, exist_ok=True)
    for k, cid in enumerate(args.ids):
        r, c = divmod(k, args.cols)
        cell = sheet.crop(
            (
                c * cw + CELL_INSET,
                r * ch + CELL_INSET,
                (c + 1) * cw - CELL_INSET,
                (r + 1) * ch - CELL_INSET,
            )
        )
        img = cut(cell)
        path = args.out / f"{cid}.png"
        img.save(path, optimize=True)
        print(f"{cid}: {img.width}x{img.height} → {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
