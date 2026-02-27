# Hook 部署機制重構 — 設計文件

## 背景與動機

現行架構使用 `.ai-review` 標記檔（放在 repo 根目錄）控制 opt-in。此方案有以下問題：

1. **在 repo 中產生新檔案** — 需決定 checkin 或加 `.gitignore`，對 200+ 個 Android repo 影響大
2. **與 Android repo tool 不協調** — manifest 不管理此檔案，開發者 `repo sync` 後仍需手動處理
3. **版控策略分歧** — 團隊統一 checkin vs. 個人 .gitignore，兩種策略各有問題

## 目標

- **零 repo 檔案污染** — 不在 repo 工作目錄產生任何新檔案
- **原生 git 機制** — hook 放在 `.git/hooks/`，opt-in 存在 `.git/config`
- **200+ repo 批次操作友善** — 支援 `repo forall -c` 和 shell loop 批次啟用
- **新 clone 自動獲得 hook** — 透過 `init.templateDir` 機制
- **向後相容** — 仍支援現行 `core.hooksPath` 全域模式和 per-repo 模式

## 設計

### 部署機制：`init.templateDir`

Git 原生的 template 機制：設定 `init.templateDir` 後，`git clone` 和 `git init` 會自動將 template 目錄中的檔案複製到 `.git/` 下。

```
~/.config/ai-code-review/template/
└── hooks/
    ├── pre-commit      # AI code review hook
    └── commit-msg      # Commit message check + AI improvement hook
```

#### 安裝流程

```bash
ai-review hook install --template
```

執行動作：
1. 建立 `~/.config/ai-code-review/template/hooks/` 目錄
2. 寫入 `pre-commit` 和 `commit-msg` hook 腳本
3. 設定 `git config --global init.templateDir ~/.config/ai-code-review/template`
4. 輸出操作結果和後續指引

#### 移除流程

```bash
ai-review hook uninstall --template
```

執行動作：
1. 刪除 template 目錄下的 hook 檔案
2. `git config --global --unset init.templateDir`

#### 既有 repo 補上 hook

`init.templateDir` 只對新 clone / 新 init 的 repo 生效。既有 repo 需執行一次 `git init`（安全操作，不影響 repo 內容）：

```bash
# 單一 repo
cd /path/to/camera-hal
git init    # 重新初始化，複製 template hooks 到 .git/hooks/

# Android repo tool 批次
repo forall -c 'git init'

# Shell loop 批次
for repo in camera-hal kernel-bsp audio-driver; do
    cd /path/to/repos/$repo && git init
done
```

> **注意**：如果 `.git/hooks/pre-commit` 或 `.git/hooks/commit-msg` 已存在，`git init` **不會覆蓋**。需先刪除舊 hook 或使用 `ai-review hook install pre-commit` 強制寫入。

### Opt-in 機制：`git config --local`

使用 git 原生的 local config 取代 `.ai-review` 標記檔：

```bash
# 啟用（存在 .git/config，不影響 repo 內容）
git config --local ai-review.enabled true

# 停用
git config --local --unset ai-review.enabled

# 查詢
git config --local ai-review.enabled
```

#### Hook 腳本中的檢查邏輯

```bash
#!/usr/bin/env bash
# Installed by ai-code-review

# opt-in: check git local config
enabled=$(git config --local ai-review.enabled 2>/dev/null)
if [ "$enabled" != "true" ]; then
    exit 0
fi

/absolute/path/to/ai-review
```

#### 批次啟用

```bash
# Android repo tool
repo forall -c 'git config --local ai-review.enabled true'

# Shell loop
for repo in camera-hal kernel-bsp audio-driver display-drm; do
    cd /path/to/repos/$repo
    git config --local ai-review.enabled true
done
```

#### 批次停用

```bash
repo forall -c 'git config --local --unset ai-review.enabled'
```

### CLI 介面變更

#### 新增 `--template` 模式

```bash
# 安裝 template hooks（推薦 Android 多 repo 團隊）
ai-review hook install --template

# 移除 template hooks
ai-review hook uninstall --template
```

#### 新增 `--enable` / `--disable` 快捷指令

```bash
# 在當前 repo 啟用 AI review（等同 git config --local ai-review.enabled true）
ai-review hook enable

# 在當前 repo 停用
ai-review hook disable

# 批次啟用（搭配 repo forall）
repo forall -c 'ai-review hook enable'
```

#### 保留現有模式

| 模式 | 指令 | 說明 |
|------|------|------|
| Template（新增） | `ai-review hook install --template` | hook 進 `.git/hooks/`，推薦 Android 專案 |
| Global（現行） | `ai-review hook install --global` | 設定 `core.hooksPath`，保留向後相容 |
| Per-repo（現行） | `ai-review hook install pre-commit` | 單一 repo 安裝 |

#### `hook status` 更新

```bash
ai-review hook status
```

輸出範例：

```
Template hooks:
  init.templateDir = /home/user/.config/ai-code-review/template
  pre-commit: installed
  commit-msg: installed

Global hooks:
  core.hooksPath: not configured

Current repo:
  ai-review.enabled = true
  .git/hooks/pre-commit: installed
  .git/hooks/commit-msg: installed
```

### 完整安裝流程（開發者視角）

```bash
# === 一次性設定（每位開發者做一次）===

# 1. 安裝工具
pip install ai-code-review

# 2. 設定 LLM provider
ai-review config set provider default ollama
ai-review config set ollama base_url http://localhost:11434
ai-review config set ollama model llama3.1

# 3. 安裝 template hooks
ai-review hook install --template

# 4. 既有 repo 補上 hook
cd /path/to/android-workspace
repo forall -c 'git init'

# 5. 批次啟用 AI review
repo forall -c 'git config --local ai-review.enabled true'

# === 完成，之後 git commit 自動觸發 ===
```

### 與現行 `.ai-review` 標記檔方案比較

| 面向 | `.ai-review` 標記檔（現行） | `git config --local`（新方案） |
|------|---------------------------|-------------------------------|
| Repo 影響 | 產生新檔案 | **零影響**，存在 `.git/config` |
| 版控問題 | 需處理 checkin vs .gitignore | **不存在** |
| Hook 位置 | `core.hooksPath` 指向全域目錄 | **`.git/hooks/`**（原生） |
| 啟用方式 | `touch .ai-review` | `git config --local ai-review.enabled true` |
| 停用方式 | `rm .ai-review` | `git config --local --unset ai-review.enabled` |
| 新 clone 自動 hook | 否（需手動 touch） | **是**（`init.templateDir` 自動複製） |
| repo tool 相容 | 需處理 manifest | **`repo forall -c` 完美支援** |
| 既有 hook 衝突 | `core.hooksPath` 覆蓋 `.git/hooks/` | **不衝突**，hook 在 `.git/hooks/` |

### 向後相容與遷移

現行 `--global`（`core.hooksPath`）模式保留不動。新增 `--template` 模式為獨立選項。

兩者**不可同時使用**：`core.hooksPath` 會覆蓋 `.git/hooks/`，導致 template hook 不被執行。安裝 `--template` 時應檢查並警告。

Hook 腳本中的 opt-in 檢查邏輯：
- `--template` 模式：檢查 `git config --local ai-review.enabled`
- `--global` 模式（現行）：保留檢查 `.ai-review` 標記檔，維持向後相容

#### 遷移路徑

從現行 `--global` 遷移到 `--template`：

```bash
# 1. 移除 global hooks
ai-review hook uninstall --global

# 2. 安裝 template hooks
ai-review hook install --template

# 3. 既有 repo 補上 hook + 啟用
repo forall -c 'git init'
repo forall -c 'git config --local ai-review.enabled true'

# 4. 移除 repo 中的 .ai-review 標記檔（選用）
repo forall -c 'rm -f .ai-review'
```

### 測試計畫

| 測試項目 | 驗證內容 |
|----------|----------|
| `hook install --template` | 建立 template 目錄、寫入 hook 腳本、設定 `init.templateDir` |
| `hook uninstall --template` | 刪除 hook 檔案、unset `init.templateDir` |
| `hook enable` / `hook disable` | 設定 / 移除 `ai-review.enabled` local config |
| `hook status` | 顯示 template、global、current repo 三種狀態 |
| Template hook + enabled | hook 正常執行 AI review |
| Template hook + disabled | hook 跳過，commit 正常 |
| Template hook + `git init` 補上 | 既有 repo 跑 `git init` 後獲得 hook |
| `--global` 與 `--template` 衝突檢查 | 同時設定時顯示警告 |
| `_resolve_ai_review_path()` | hook 腳本使用絕對路徑，venv 環境可用 |

### 影響範圍

#### 需修改的檔案

| 檔案 | 變更 |
|------|------|
| `src/ai_code_review/cli.py` | 新增 `--template`、`enable`、`disable` 指令；更新 `hook status` |
| `tests/test_hooks.py` | 新增 template hook 相關測試 |
| `docs/SOP.md` | 更新安裝和使用流程 |
| `README.md` | 更新 hook setup 段落 |
| `CLAUDE.md` | 更新 hook deployment 說明 |

#### 不需修改的檔案

- `config.py` — 不涉及 config 結構變更
- `git.py` — 不涉及 git diff 邏輯
- `reviewer.py`, `prompts.py`, `formatters.py` — 不涉及
- `llm/` — 不涉及
