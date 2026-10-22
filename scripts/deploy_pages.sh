#!/usr/bin/env bash
# 把 dist/ 推到 gh-pages 分支（GitHub Pages 用）。先跑 scripts/build_site.py。
#
# 用法：scripts/deploy_pages.sh
# 第一次要在 GitHub 的 Settings → Pages 把來源設成 gh-pages 分支（根目錄）。
set -euo pipefail

cd "$(dirname "$0")/.."
[[ -f dist/index.html ]] || { echo "沒有 dist/，先跑 uv run scripts/build_site.py"; exit 1; }
remote=$(git remote get-url origin)
sha=$(git rev-parse --short HEAD)

tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT
cp -r dist/. "$tmp"/
cd "$tmp"
git init -q
git checkout -q -b gh-pages
git add -A
git -c user.name="deploy" -c user.email="deploy@local" commit -q -m "deploy: site from $sha"
git push -f "$remote" gh-pages
echo "已推到 gh-pages；網址通常是 https://<帳號>.github.io/<repo>/"
