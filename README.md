# reader-theater

英文劇場的虛擬劇場：3D 角色依台詞音訊對嘴。

## 網站（漫畫版，點一句唸一句）

https://grasonyang.github.io/reader-theater/ — 背景與角色是 AI 生成的美式漫畫風圖片，點畫面或按空白鍵唸下一句；加 `?mode=auto` 自動演完，`?scene=s2` 只演一場。3D 版在 `theater3d.html`。

更新網站：`uv run scripts/build_site.py && scripts/deploy_pages.sh`（第一次要在 GitHub Settings → Pages 把來源設成 `gh-pages` 分支）。

## 快速開始

```bash
npm ci
scripts/fetch_avatar.sh          # 下載範例角色（CC BY-NC 4.0）
scripts/prep_scenes.sh           # 從原始錄音重建台詞音訊（需要 uv、ffmpeg）
npm run dev                      # 開 http://localhost:5173，按「播放台詞」；?script=missing-duck 演整齣
```

| 指令 | 用途 |
|---|---|
| `uv run scripts/prep_audio.py <音檔> -o <輸出.wav> [--denoise]` | 人聲清晰化（EQ、壓縮、去齒音）、-16 LUFS、48 kHz 單聲道，並產生逐字時間戳 JSON。錄音環境吵雜時加 `--denoise` |
| `uv run scripts/align_lines.py <劇本.json> <場次> <整場.wav> --report <報告.md>` | 把整場錄音切成一句一句、對回劇本，寫回 audio／timestamps，並列出念錯、漏念 |
| `npm run record` | 無頭瀏覽器逐格算圖，輸出 5 秒的 `preview.mp4` |
| `node scripts/record_scene.mjs <劇本名稱> [場次] -o <輸出.mp4> [--page comic.html]` | 逐格算圖整場或整齣演出；`--page comic.html` 錄漫畫版 |
| `uv run scripts/cut_sheet.py <角色表圖> assets/art/characters <角色 id...>` | 綠幕角色表去背、切成一人一張 PNG |
| `uv run scripts/build_site.py` / `scripts/deploy_pages.sh` | 打包靜態網站（音訊轉 mp3）並推到 gh-pages |

| `uv run scripts/role_voices.py <劇本.json>` | 一人分飾多角：依角色設定變聲，輸出 `<名稱>-voices.json` |
| `scripts/prep_scenes.sh [劇本名稱]` | 從 repo 裡的原始錄音重建每句音訊與時間戳（clone 後跑一次，網頁才能演） |
| `scripts/spark_clone.sh` | 在 GPU 機器上用 F5-TTS 複製你的聲音，輸出 `<名稱>-clone.json`（見 docs/voice-clone.md） |

網頁加 `?script=<名稱>&scene=<場次>` 會演 `assets/scripts/<名稱>.json`（例：`?script=missing-duck&scene=s1`）。

原稿、錄音、角色模型等素材的位置與取得方式見 [docs/sources.md](docs/sources.md)。

需要 Node 22、uv、ffmpeg。劇本格式見 [docs/script-schema.md](docs/script-schema.md)，授權見 [docs/licenses.md](docs/licenses.md)。

---

以下是 agent 設定（由 agent-config 模板帶入）。

## agent-config

Yang-Home-99 的 AI agent 設定中心，涵蓋 Claude Code 與 Codex。

## 結構
| 路徑 | 用途 |
|---|---|
| `AGENTS.md` | 兩邊共用的指令（單一來源） |
| `CLAUDE.md` | 匯入 `AGENTS.md`，加上 Claude 專屬內容 |
| `docs/agents/skill-routing.md` | 情境到 skill 的路由、來源解析、宣告格式 |
| `docs/agents/workflow.md` | 以 Matt skills 為基準的開發流程 |
| `docs/agents/delivery.md` | 追蹤、交接格式、worktree 與 Git、升級規則 |
| `docs/agents/issue-tracker.md`、`triage-labels.md`、`domain.md` | Matt skills 的專案設定（已預先完成） |
| `docs/agents/dev-env.md` | Python（uv）、Rust（cargo）的環境與驗證指令 |
| `docs/agents/roles.md` | planner、worker、reviewer 三個標準角色 |
| `.claude/agents/` | Claude 的三個 agent（`planner.md`、`worker.md`、`reviewer.md`） |
| `.codex/` | Codex 設定與三個 agent（`agents/*.toml`） |
| `.github/` | Issue 表單（Task、Bug、Feature、Spec、Decision、Research、Chore）、PR 範本、標籤清單 |
| `scripts/` | `sync-labels.sh` 同步標籤、`project-status.sh` 設定看板欄位 |

## 使用方式

這是 GitHub template repo。建新專案：

```bash
gh repo create Yang-Home-99/<名稱> --template Yang-Home-99/agent-config --private --clone
cd <名稱> && scripts/sync-labels.sh
```

建好後依 `docs/agents/dev-env.md` 初始化語言環境（Python 用 uv，Rust 用 cargo），並在專案 `AGENTS.md` 補上「驗證指令」區塊。

## 相關
- Skills：[Yang-Home-99/matt-skills](https://github.com/Yang-Home-99/matt-skills)（fork 自 mattpocock/skills）
- 看板：[開發看板](https://github.com/orgs/Yang-Home-99/projects/1)
- 研究：[Yang-Home-99/research](https://github.com/Yang-Home-99/research)
