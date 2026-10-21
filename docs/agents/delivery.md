# 交付：追蹤、交接與 Git

planner、worker、reviewer 之間怎麼交接，工作怎麼記錄，程式碼怎麼進主幹。角色定義見 [roles.md](./roles.md)，流程順序見 [workflow.md](./workflow.md)。

## 追蹤系統

- **Issue 是交接契約本身**，放在各 repo 的 GitHub Issues。操作方式見 [issue-tracker.md](./issue-tracker.md)。
- **org Project「開發看板」只是視圖**，跨 repo 彙整 sprint 與狀態。看板上的資料不當作事實來源，以 issue 為準。
- 不用 Linear。Matt skills 對 GitHub 有完整的操作範本（sub-issue、原生依賴、標籤），Linear 沒有。

### 看板欄位

| 欄位 | 選項 |
|---|---|
| Status | Backlog、Ready、In progress、In review、Done |
| Priority | P0 阻塞或緊急、P1 本 sprint 必做、P2 有空就做、P3 暫不處理 |
| Size | XS、S、M、L、XL（XL 必須拆成多張 ticket） |
| Sprint | 兩週一輪，已建 Sprint 1 到 4（從 2026-10-21 起） |

用腳本設定欄位（會自動把 issue 或 PR 加進看板，可重複執行）：

```bash
scripts/project-status.sh <issue 或 PR 的 URL> Status="In progress" Priority=P1 Size=S Sprint="Sprint 1"
```

看板的內建自動化（新增 issue 自動加入、關閉時自動設為 Done）無法由 API 設定，需要在網頁的 Project 設定的 Workflows 裡手動開啟。沒開之前，由協調者用腳本維護。

### Issue 類別

| 類別 | 怎麼標記 | 來源 | 用途 |
|---|---|---|---|
| Task | Issue type | `to-tickets` | 一張 tracer-bullet ticket |
| Bug | Issue type | 人或 `triage` | 非預期的行為 |
| Feature | Issue type | 人或 `triage` | 新功能的想法 |
| Spec | Issue type | `to-spec` | 規格 |
| Decision | Issue type | `wayfinder`、`grill-with-docs` | 待定案的決策，ADR 候選 |
| Research | Issue type | `research` | 查證與調查 |
| Chore | Issue type | 人 | 依賴、設定、重構、CI |

七個類別都是 org 的 Issue type，建立時用 `gh issue create --type <類別>`。每個類別在 `.github/ISSUE_TEMPLATE/` 都有對應的網頁表單。

### 狀態流轉

| 變化 | 誰做 | 時機 |
|---|---|---|
| Backlog 到 Ready | planner 或協調者 | 規格完整、blocker 全部關閉、加上 `ready-for-agent` |
| Ready 到 In progress | worker 認領 | 建好 worktree，並 `--add-assignee @me` |
| In progress 到 In review | worker | PR 已開、交付報告已貼 |
| In review 到 Done | 協調者 | 使用者確認合併後 |

## 交接契約

### 1. Ticket（planner 交給 worker）

正文格式照 `to-tickets`，用 Issue form 的 Task：

```markdown
## Parent
#<上層編號>（沒有就省略）

## What to build
從使用者角度描述做完後能做到什麼，不寫逐層實作清單，不寫會過期的檔案路徑。

## Acceptance criteria
- [ ] ...

## Blocked by
原生依賴已設定時，省略這一段。
```

規則：一張 ticket 一個 worktree；blocker 要用原生依賴連結；XL 要拆；ticket 有疑問，worker 回報而不是自己改 spec。

### 2. 交付報告（worker 交給 reviewer 與協調者）

寫在 PR 描述（`.github/PULL_REQUEST_TEMPLATE.md`）加一則 issue 留言，內容固定：

```markdown
## 交付報告
- **Ticket**：#<n>
- **範圍**：<base>..HEAD
- **改了什麼**：<一到三句，用 GLOSSARY.md 的用語>
- **驗證**（專案「驗證指令」區塊的實際輸出）：
  - 格式：<指令> → <通過或失敗>
  - 靜態檢查：<指令> → <結果>
  - 測試：<指令> → <結果，例如 42 passed>
- **未決項目**：<沒有就寫「無」>
- **使用的 Skill**：<清單>
```

### 3. 審查報告（reviewer 交給協調者）

以 PR review 或 issue 留言送出，一份報告只審一軸：

```markdown
## 審查報告
- **軸**：Standards 或 Spec
- **範圍**：<base>..HEAD
- **結論**：通過，或需要修改
- **問題**（沒有就寫「無」）：
  1. [blocker|major|minor|nit] `檔案:行`：<原因>。建議：<做法>
- **使用的 Skill**：<清單>
```

嚴重度：blocker 不修不能合併；major 應該修；minor、nit 由 worker 判斷。

## Worktree 與 Git

**任何改動都先開新 worktree**，包括文件的一行小修。一張 issue 對一個 worktree、一個 branch、一個 PR。

| 項目 | 規則 |
|---|---|
| 名稱 | `<issue 編號>-<短英文 slug>`，例如 `12-add-roles` |
| Worktree 位置 | `<repo>/.claude/worktrees/<名稱>`（已被 `.gitignore` 忽略），與 Claude Code 的預設一致 |
| Branch | 與名稱相同，從 `origin/main` 開出 |
| 建立 | `git fetch origin && git worktree add .claude/worktrees/<名稱> -b <名稱> origin/main` |
| 開工後 | 在 worktree 內先跑專案「驗證指令」的「安裝」 |
| Commit | 一句話描述「做了什麼與為什麼」；Claude 的 commit 附 `Co-Authored-By` |
| PR | 標題簡短，內文用 PR 範本，`Closes #<n>`；單向門加標籤 `one-way-door` |
| 合併 | 協調者在使用者確認後 squash merge，主幹保持線性 |
| 清理 | 合併後 `git worktree remove .claude/worktrees/<名稱>` 並刪除 branch |
| 不要 | 在 main 上直接 commit、`git push --force`、改寫已推送的歷史 |

初始化階段（本文件建立之前）的提交直接進 main，這是唯一例外。

## 升級規則

停下來、回報給使用者，不要硬撐：

- worker 對同一個失敗修了 2 輪仍未解決，回報卡點與證據。
- reviewer 與 worker 來回超過 2 輪仍不同意，交給使用者裁決。
- 發現需要改 spec、ticket 範圍或介面，回到 planner，不在實作中悄悄改。
- 要做破壞性或對外可見的動作（刪除、覆寫、推送、發佈、付費額度）。
- 需要的 skill 找不到來源（見 [skill-routing.md](./skill-routing.md)）。

## 輕量路徑

同時符合下列全部條件，可以略過 `grill-with-docs`、`to-spec`、`to-tickets`：

- 影響不超過約 30 行，且不改行為或介面。
- 沒有新依賴，沒有資料遷移。
- 做完能立刻用驗證指令確認。

例：錯字、文件小修、設定值調整。仍然要：開 worktree 與 branch、跑驗證指令、開 PR。Issue 可以只是一行 Chore。

## 知識放哪裡

| 內容 | 放哪裡 |
|---|---|
| 專案用語、ADR、spec、ticket、PR | 專案 repo（事實來源） |
| 跨專案的工作規範、角色、流程 | 本模板 repo（`agent-config`） |
| session 檢查點、研究結論摘要、踩雷與環境筆記 | Basic Memory（`sessions/`、`infra/`、`projects/<專案>`） |
| 有替代方案與理由的研究決策 | 專案的 ADR；Basic Memory 的 `decisions/` 只放摘要並連到 ADR |
| `retro` 的環境改善建議 | 開成 `agent-config` 的 issue，經過同一套流程修改 |

## 模板機制

目前階段：`agent-config` 是 GitHub template repo，建新專案用 `gh repo create <名稱> --template Yang-Home-99/agent-config --private --clone`。

- 模板只複製一次，不會跟著上游更新。`agent-config` 之後的修改要手動帶進既有專案。
- 語言層（uv、Rust）尚未做成模板；建好專案後依 [dev-env.md](./dev-env.md) 初始化。
- 之後若漂移成問題，再評估改用 `copier`，它有 `copier update` 可以拉回上游修改。
