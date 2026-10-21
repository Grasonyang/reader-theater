# reader-theater

英文劇場的虛擬劇場：3D 角色依台詞音訊對嘴。

## 快速開始

```bash
npm ci
scripts/fetch_avatar.sh          # 下載範例角色（CC BY-NC 4.0）
npm run dev                      # 開 http://localhost:5173，按「播放台詞」
```

| 指令 | 用途 |
|---|---|
| `uv run scripts/prep_audio.py <音檔> -o <輸出.wav> [--denoise]` | 人聲清晰化（EQ、壓縮、去齒音）、-16 LUFS、48 kHz 單聲道，並產生逐字時間戳 JSON。錄音環境吵雜時加 `--denoise` |
| `npm run record` | 無頭瀏覽器逐格算圖，輸出 5 秒的 `preview.mp4` |

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
