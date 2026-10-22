# 漫畫版圖片的生成 prompt

2026-10-21 用 AI 生圖工具產生，原圖在 `assets/art/source/`。要重生或補圖時沿用同一套風格描述。

## 共用風格（每個 prompt 開頭）

```
American superhero comic book art style, Marvel-inspired: bold black ink outlines, flat saturated colors with cel shading, visible halftone dot shading, dynamic composition, clean and polished, no text, no speech bubbles, no watermark.
```

## 背景（16:9）

每張加上：`wide shot, no people, no characters, lower third of the image kept simple for a dialogue box overlay.`

| 檔名 | 內容 |
|---|---|
| `s1` | Interior of a bright American junior high school basketball gym, polished wooden floor with court lines, bleachers, a basketball hoop, championship banners on the wall, and an empty glass trophy case with its door open, morning light through high windows. |
| `s2` | Same gym, low angle view under and beside the bleachers, a few scattered popcorn pieces and a single white feather on the wooden floor, a wet footprint, dramatic shadows. |
| `s3` | A dim, cluttered school storage room next to a gym: shelves with basketballs, cones and mats, a single ceiling bulb, a small open window above the door letting in light, a shiny gold trophy on the floor full of popcorn, a small white duck sitting beside it. |
| `s4` | The same bright gym, the gold trophy back inside the glass trophy case, shiny and clean, confetti in the air, festive and warm lighting. |

## 角色表（綠幕，2×2）

```
Character sheet on a plain solid bright green background (#00FF00), no shadows on the background, no text, no labels. Full body from head to knees, facing slightly toward the viewer.
```

| 格子 | 角色 | 描述 |
|---|---|---|
| 左上 | Mia | A 13-year-old girl, confident and calm detective look, long dark brown hair, red hooded jacket over a dark blue skirt, holding a magnifying glass, slight knowing smile. |
| 右上 | Ben | A 13-year-old boy, nervous and jumpy expression, messy blond hair, green t-shirt, dark jeans, hands raised slightly as if worried, wide eyes. |
| 左下 | Coach Lee | A tall Asian-American man in his 40s, basketball coach, short black hair, navy blue tracksuit with white stripes, a silver whistle on a lanyard, strong build, stern but kind face. |
| 右下 | Sam | A shy 7-year-old boy, small and cute, brown hair, yellow t-shirt and grey shorts, holding a small bag of popcorn, bashful expression. |

切圖：`uv run scripts/cut_sheet.py assets/art/source/characters-sheet.webp assets/art/characters mia ben coach-lee sam`

## 之後想補的

- 每個角色一張「張嘴」版（同姿勢、只改嘴巴），做嘴型開合。
- 每個角色兩三種表情（驚訝、害怕、開心）。
