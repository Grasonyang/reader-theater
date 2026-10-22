#!/usr/bin/env bash
# 下載 TalkingHead 的範例角色 brunette.glb 到 public/avatars/。
# 授權：CC BY-NC 4.0（Ready Player Me），只限非商業使用，見 docs/licenses.md。
# 不放進版控，每個 worktree 開工後跑一次。
set -euo pipefail

cd "$(dirname "$0")/.."
dest=public/avatars/brunette.glb
url=https://raw.githubusercontent.com/met4citizen/TalkingHead/main/avatars/brunette.glb

if [[ -f "$dest" ]]; then
  echo "已存在：$dest"
  exit 0
fi
mkdir -p "$(dirname "$dest")"
curl -sSfL -o "$dest.tmp" "$url"
mv "$dest.tmp" "$dest"
echo "已下載：$dest"
