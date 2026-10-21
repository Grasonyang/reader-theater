#!/usr/bin/env bash
# 在有 NVIDIA GPU 的機器（例如 DGX Spark）上，從四個場次的錄音做出「複製聲音」版劇本。
#
# 用法：scripts/spark_clone.sh
#   用 repo 裡的原始錄音 assets/audio/voice/missing-duck/raw/scene<N>.*
#
# 步驟：
#   1. 檢查 ffmpeg、uv、PyTorch 是否看得到 GPU
#   2. scripts/prep_scenes.sh：每場錄音清晰化、產生時間戳、對回劇本（產生參考音檔）
#   3. clone_voice.py 用 F5-TTS 依劇本合成每句，再對齊成 missing-duck-clone.json
#
# 沒有 GPU 也想跑（很慢）：ALLOW_CPU=1 scripts/spark_clone.sh
set -euo pipefail

cd "$(dirname "$0")/.."
script=assets/scripts/missing-duck.json

command -v ffmpeg >/dev/null || { echo "缺 ffmpeg：sudo apt install -y ffmpeg"; exit 1; }
command -v uv >/dev/null || { echo "缺 uv：curl -LsSf https://astral.sh/uv/install.sh | sh"; exit 1; }

echo "== 檢查 GPU"
if ! uv run --python 3.12 --with torch python -c '
import sys, torch
ok = torch.cuda.is_available()
print("torch", torch.__version__, "CUDA" if ok else "沒有 CUDA", torch.cuda.get_device_name() if ok else "")
sys.exit(0 if ok else 1)
'; then
  if [[ "${ALLOW_CPU:-}" != 1 ]]; then
    echo "PyTorch 看不到 GPU。可以改在 NGC PyTorch 容器裡跑（見 docs/voice-clone.md），或設 ALLOW_CPU=1 用 CPU 跑。"
    exit 1
  fi
fi

echo "== 清晰化、時間戳、對齊（你的原始錄音）"
scripts/prep_scenes.sh missing-duck

echo "== 合成（F5-TTS）"
uv run --python 3.12 scripts/clone_voice.py "$script"

echo
echo "完成。預覽：npm run dev 後開 http://localhost:5173/?script=missing-duck-clone"
echo "算成影片：node scripts/record_scene.mjs missing-duck-clone -o missing-duck-clone.mp4"
