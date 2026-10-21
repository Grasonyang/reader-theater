# 開發環境

各語言的標準工具鏈與驗證指令。Python 以 **uv** 為基礎，Rust 以 **rustup + cargo** 為基礎。新增語言時比照下方格式補一節：工具鏈、鎖檔、驗證指令。

## 共通原則

- 一個語言只用一套工具鏈，不混用（Python 不用 pip、poetry；Rust 不用自訂 build 腳本取代 cargo）。
- 環境可重現：版本釘在檔案裡、鎖檔進版控、指令從專案根目錄執行。
- 不依賴全域安裝：lint、型別檢查、測試工具都作為專案的 dev 依賴，agent 在乾淨的 worktree 裡就能跑。
- 每個 worktree 各自有一份環境（`.venv`、`target/`）。開 worktree 後先跑下方的「安裝」指令。

### 驗證指令（完成定義的一部分）

專案的 `AGENTS.md` 必須有一個固定區塊，宣告該專案的驗證指令。worker 交付前全部跑過並附上結果；reviewer 以交付報告為準，必要時重跑。

```markdown
## 驗證指令
- 安裝：<指令>
- 格式：<指令>
- 靜態檢查：<指令>
- 測試（全部）：<指令>
- 測試（單檔）：<指令>
```

下面兩節給出各語言的預設值，專案可以覆寫，但要寫在上面的區塊。

## Python（uv）

### 專案結構
- `uv init` 建專案（函式庫用 `uv init --package`，採 `src/` 配置）。
- `pyproject.toml` 是唯一設定來源；`uv.lock` 與 `.python-version` 進版控。
- Python 版本用 `uv python pin` 釘在 `.python-version`，由專案決定，不依賴系統 Python。
- 測試放 `tests/`。

### 日常指令
| 目的 | 指令 |
|---|---|
| 加依賴 | `uv add <pkg>` |
| 加開發依賴 | `uv add --dev <pkg>` |
| 移除 | `uv remove <pkg>` |
| 執行 | `uv run <cmd>`（不手動 activate venv） |
| 全域 CLI 工具 | `uv tool install <tool>` |

- 不用 `pip install`，不手動編輯 `uv.lock`。
- 單檔腳本（實驗、研究用）用 PEP 723 內嵌依賴，`uv run script.py` 直接跑，不需要建專案。`research` repo 優先這樣做。

### 預設工具
- 格式與 lint：**ruff**
- 型別檢查：**pyright**（想換成別的就在專案 `AGENTS.md` 的驗證區塊改掉）
- 測試：**pytest**

### 驗證指令預設值
```markdown
- 安裝：`uv sync --locked`
- 格式：`uv run ruff format --check .`
- 靜態檢查：`uv run ruff check . && uv run pyright`
- 測試（全部）：`uv run pytest`
- 測試（單檔）：`uv run pytest path/to/test_x.py`
```
`--locked` 在 `uv.lock` 與 `pyproject.toml` 不一致時會失敗，agent 因此不會悄悄改到鎖檔。

## Rust（rustup + cargo）

### 專案結構
- `cargo new` 建專案；多個 crate 用 workspace，依賴版本統一寫在 `[workspace.dependencies]`，lint 設定寫在 `[workspace.lints]`。
- 根目錄放 `rust-toolchain.toml`，釘住 channel，並列出 `rustfmt`、`clippy` 兩個 component。
- `Cargo.lock` 一律進版控。

### 日常指令
| 目的 | 指令 |
|---|---|
| 加依賴 | `cargo add <crate>` |
| 建置 | `cargo build --workspace` |
| 執行 | `cargo run -p <crate>` |

### 驗證指令預設值
```markdown
- 安裝：`cargo fetch --locked`
- 格式：`cargo fmt --all --check`
- 靜態檢查：`cargo clippy --workspace --all-targets --locked -- -D warnings`
- 測試（全部）：`cargo test --workspace --locked`
- 測試（單檔）：`cargo test -p <crate> --test <name>`
```
- `-D warnings` 讓 clippy 警告直接變成失敗，避免警告累積。
- `cargo-nextest` 可以加速測試，但它不跑 doctest，使用時要另外跑 `cargo test --doc`。目前本機未安裝，需要時再加。

### Worktree 注意
每個 worktree 預設各有自己的 `target/`，首次建置會比較久且佔空間。磁碟吃緊時可以讓多個 worktree 共用 `CARGO_TARGET_DIR`，代價是同時建置會互相等鎖，切換分支也會重新編譯。

## 共用工具基線

核對日期：2026-10-21，本機實際版本。

| 工具 | 版本 | 備註 |
|---|---|---|
| git、gh | gh 2.102.1 | 來源是 GitHub 官方 apt（已用 apt pin 優先於 Ubuntu 的 2.45.0）。`--type`、`--parent`、`--add-blocked-by`、`--add-sub-issue` 需要 2.102 以上。 |
| uv | 0.9.15 | Python 的唯一入口 |
| rustup、cargo | cargo 1.94.1、rustup 1.29.0 | 已含 `clippy`、`rustfmt` |
| ruff、pyright | 未全域安裝 | 作為各專案的 dev 依賴 |
| cargo-nextest、cargo-deny | 未安裝 | 選用 |

版本更新後請回來改這張表。
