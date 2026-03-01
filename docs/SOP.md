# AI Code Review — 安裝與使用 SOP

## 一、安裝

### 前置需求

| 項目 | 需求 | 確認指令 |
|------|------|----------|
| Python | 3.10 以上 | `python3 --version` |
| Git | 任意版本 | `git --version` |
| pip | 任意版本 | `pip --version` |
| Ollama（選用） | 本地 LLM 推理 | `ollama --version` |

### Step 1：安裝 ai-review

如果尚未安裝 Python 3.10+：

```bash
# Ubuntu/Debian
sudo apt update && sudo apt install python3 python3-pip python3-venv

# macOS (Homebrew)
brew install python@3.12
```

從原始碼安裝：

```bash
# GitHub
git clone https://github.com/seen0722/ai-code-review.git

# 或內網 GitLab（替換為實際 URL）
# git clone https://gitlab.internal.company.com/bsp-tools/ai-code-review.git

cd ai-code-review
python3 -m venv .venv
source .venv/bin/activate
pip install .
```

或直接安裝（不需 clone）：

```bash
pip install git+https://github.com/seen0722/ai-code-review.git
```

驗證：`ai-review --help`

### Step 2：設定 LLM Provider

選擇一種：

```bash
# 方案 A：本地 Ollama（推薦內網）
ai-review config set provider default ollama
ai-review config set ollama base_url http://localhost:11434
ai-review config set ollama model llama3.1

# 方案 B：企業內部 LLM
ai-review config set provider default enterprise
ai-review config set enterprise base_url https://llm.internal.company.com
ai-review config set enterprise api_path /v1/chat/completions
ai-review config set enterprise model internal-codellama-70b
ai-review config set enterprise auth_type bearer
ai-review config set enterprise auth_token_env ENTERPRISE_LLM_KEY

# 方案 C：OpenAI（精確度最高，建議用 gpt-4o）
ai-review config set provider default openai
ai-review config set openai api_key_env OPENAI_API_KEY
ai-review config set openai model gpt-4o
```

驗證：`ai-review config get provider default`

### Step 3：安裝 Hooks

```bash
ai-review hook install --template
```

這會設定 `init.templateDir`，之後新 clone 的 repo 自動帶有 hooks（放在 `.git/hooks/`）。

既有 repo 補上 hooks：

```bash
# Android repo 專案
repo forall -c 'git init'

# 或個別 repo
cd /path/to/camera-hal && git init
```

### Step 4：啟用 AI Review

Hooks 預設不啟用，需在每個 repo 設定 opt-in（存在 `.git/config`，不產生任何 repo 檔案）：

```bash
# 單一 repo
ai-review hook enable

# 批次啟用
repo forall -c 'ai-review hook enable'
```

### Step 5（選用）：調整審查副檔名

預設只審查 `c, cpp, h, hpp, java`。如需調整：

```bash
ai-review config set review include_extensions "c,cpp,h,hpp,java,kt"
```

### Step 6（選用）：新增自訂審查規則

在預設 BSP 審查規則之外，追加專案特定的檢查項目：

```bash
ai-review config set review custom_rules "Also check for integer overflow, use-after-free, and double-free"
```

驗證：`ai-review config get review custom_rules`

自訂規則會附加在預設 prompt 後面，未設定時行為與預設完全相同。

### 安裝檢查清單

- [ ] `ai-review --help` 正常顯示
- [ ] `ai-review config get provider default` 顯示已設定的 provider
- [ ] `ai-review health-check` 驗證 LLM provider 連線正常
- [ ] `ai-review config show` 確認設定正確
- [ ] `ai-review hook status` 顯示 template hooks installed
- [ ] 需要 AI review 的 repo 已執行 `ai-review hook enable`

---

## 二、日常使用

### 自動觸發（推薦）

啟用後，`git commit` 自動執行：

```
git commit
  |
  +-- 檢查 ai-review.enabled -- 未啟用則跳過
  |
  +-- [Hook 1] pre-commit: AI Code Review
  |   PASS  無嚴重問題 -- 繼續
  |   BLOCK 發現 critical/error -- 擋下 commit
  |
  +-- [Hook 2] prepare-commit-msg: 自動產生 Commit Message
  |   根據 staged diff 用 AI 產生描述，自動前綴 [PROJECT-ID]
  |   填入編輯器供確認/修改（使用 -m 時跳過）
  |
  +-- [Hook 3] commit-msg: 格式檢查 + AI 英文優化
  |   PASS  格式正確 -- AI 改善英文描述（自動接受）
  |   BLOCK 格式錯誤 -- 擋下 commit
  |
  +-- Commit 成功
```

`git push` 自動執行：

```
git push origin main
  |
  +-- [Hook] pre-push: AI Review 所有待推送 commits
  |   PASS  無嚴重問題 -- 繼續 push
  |   BLOCK 發現 critical/error -- 擋下 push
  |
  +-- Push 成功
```

所有 hooks 使用 `--graceful` 模式：LLM 連線失敗時只印警告，不阻擋操作。

### Commit Message 規範

#### 格式要求

所有 commit message 必須符合 `[PROJECT-NUMBER] description` 格式：

```
[BSP-456] fix camera HAL null pointer crash
[CAM-123] add frame rate control for preview
[AUDIO-78] resolve mixer path leak on close
```

不符合格式的 commit 會被 commit-msg hook 直接擋下：

```
fix bug                          -- 擋下：缺少 [PROJECT-NUMBER]
[bsp-456] fix crash              -- 擋下：專案代碼須為大寫
update driver                    -- 擋下：缺少 [PROJECT-NUMBER]
```

#### AI 英文優化

格式檢查通過後，AI 會根據 staged diff 自動改善 commit message：

- 修正英文文法與拼寫錯誤
- 根據實際程式碼變更讓描述更精確
- Hook 模式下自動接受 AI 建議（`--auto-accept`）

#### 手動執行

```bash
# 檢查並改善指定的 commit message 檔案
ai-review check-commit .git/COMMIT_EDITMSG

# 自動接受 AI 建議（非互動模式）
ai-review check-commit --auto-accept .git/COMMIT_EDITMSG
```

互動模式下會顯示 AI 建議，提供三個選項：

| 選項 | 說明 |
|------|------|
| **[A]ccept** | 接受 AI 建議，覆寫 commit message |
| **[E]dit** | 開啟編輯器修改 AI 建議 |
| **[S]kip** | 保留原始 commit message |

設定環境變數 `AI_REVIEW_AUTO_ACCEPT=1` 可全域啟用自動接受。

### 自動產生 Commit Message

prepare-commit-msg hook 會根據 staged diff 用 AI 自動產生 commit message：

- 使用 `git commit`（不帶 `-m`）時觸發
- 使用 `-m` 提供 message 時自動跳過
- 若設定 `commit.project_id`，自動前綴 `[PROJECT-ID]`

設定專案 ID：

```bash
ai-review config set commit project_id "BSP-456"
```

手動產生 commit message：

```bash
ai-review generate-commit-msg .git/COMMIT_EDITMSG
```

### Pre-push 審查

`git push` 時自動對所有待推送的 commits 執行 AI code review：

- 發現 critical/error 等級問題時擋下 push
- warning/info 等級只提示，不阻擋
- 使用 `--graceful` 模式，LLM 連線失敗時不阻擋 push

手動執行 pre-push 審查：

```bash
ai-review pre-push
```

### 手動 Code Review

```bash
git add kernel/drivers/gpu/drm/panel-samsung.c
ai-review                    # terminal 輸出
ai-review -v                 # debug logging（排查問題用）
ai-review --format markdown  # Markdown（貼 Issue）
ai-review --format json      # JSON（CI/CD 整合）
```

### 檢查設定與連線

```bash
ai-review config show             # 檢視所有設定
ai-review config show openai      # 檢視單一 section
ai-review health-check            # 驗證 LLM provider 連線
```

### 跳過 Hooks

```bash
git commit --no-verify -m "[HOTFIX-001] emergency fix"
```

### 啟用 / 停用 Repo

```bash
ai-review hook enable           # 啟用
ai-review hook disable          # 停用
repo forall -c 'ai-review hook enable'   # 批次啟用
repo forall -c 'ai-review hook disable'  # 批次停用
```

---

## 三、設定參考

設定檔：`~/.config/ai-code-review/config.toml`

```toml
[provider]
default = "ollama"

[ollama]
base_url = "http://localhost:11434"
model = "llama3.1"
timeout = 120              # HTTP timeout（秒），預設 120

[review]
include_extensions = "c,cpp,h,hpp,java"
max_diff_lines = 2000      # diff 行數上限，超過會截斷，預設 2000
custom_rules = "Also check for integer overflow and use-after-free"

[commit]
project_id = "BSP-456"     # 自動產生 commit message 時前綴 [PROJECT-ID]

[openai]
api_key_env = "OPENAI_API_KEY"
model = "gpt-4o"
timeout = 60               # 選用，預設 120

[enterprise]
base_url = "https://llm.internal.company.com"
api_path = "/v1/chat/completions"
model = "internal-codellama-70b"
auth_type = "bearer"
auth_token_env = "ENTERPRISE_LLM_KEY"
timeout = 120              # 選用，預設 120
```

### 審查等級

| 等級 | 說明 | 擋下 Commit |
|------|------|:-----------:|
| critical | 安全漏洞、資料洩漏 | **是** |
| error | 明顯 bug、邏輯錯誤 | **是** |
| warning | 潛在問題 | 否 |
| info | 一般建議 | 否 |

### 審查重點（BSP 導向）

AI 只聚焦嚴重問題，**不報告**程式碼風格或命名建議：

- 記憶體洩漏（malloc/free 不匹配）
- Null pointer 解引用
- Race condition
- Hardcoded 密碼/金鑰
- Buffer overflow
- 資源未釋放（file descriptor、socket）

---

## 四、常見問題

**Q: 安裝後所有 repo 都會被影響嗎？**
不會。只有執行 `ai-review hook enable` 的 repo 才會觸發 AI review。

**Q: 誤報太多怎麼辦？**
小型模型（llama3.1:7b）可能產生誤報。建議用更大模型（70b+）或 OpenAI GPT-4o。單次跳過：`git commit --no-verify`。

**Q: 多人共用 Ollama？**
在伺服器啟動 Ollama，其他人設定：`ai-review config set ollama base_url http://192.168.1.100:11434`

**Q: 網路不穩定，LLM 呼叫常失敗？**
ai-review 內建 HTTP 重試機制（自動重試 3 次）。如果仍然失敗，可調整 timeout：`ai-review config set ollama timeout 180`。使用 `ai-review -v` 查看詳細 debug log。

**Q: diff 太大，LLM 回應很慢或超時？**
預設限制 diff 最多 2000 行。如需調整：`ai-review config set review max_diff_lines 5000`。超過上限時會自動截斷並警告。

**Q: LLM 連線失敗會擋下 commit/push 嗎？**
不會。所有 hooks 使用 `--graceful` 模式，LLM 連線失敗時只印警告，不阻擋操作。格式驗證（如 commit message 格式）不受影響，仍會正常擋下。

**Q: 如何完全移除？**

```bash
ai-review hook uninstall --template
pip uninstall ai-code-review
rm -rf ~/.config/ai-code-review
```

---

## 五、快速安裝腳本

存為 `setup-ai-review.sh` 發給團隊：

```bash
#!/usr/bin/env bash
set -e
REPO_URL="${AI_REVIEW_REPO:-https://github.com/seen0722/ai-code-review.git}"
INSTALL_DIR="${HOME}/ai-code-review"

echo "=== AI Code Review Setup ==="
git clone "$REPO_URL" "$INSTALL_DIR"
cd "$INSTALL_DIR"
python3 -m venv .venv
source .venv/bin/activate
pip install .
ai-review config set provider default ollama
ai-review config set ollama base_url "${OLLAMA_URL:-http://localhost:11434}"
ai-review config set ollama model "${OLLAMA_MODEL:-llama3.1}"
ai-review hook install --template
echo ""
echo "=== Setup Complete ==="
echo "Enable repos: repo forall -c 'git init && ai-review hook enable'"
echo "Skip once:    git commit --no-verify"
```

```bash
# 使用（GitHub）
bash setup-ai-review.sh

# 使用（內網 GitLab）
AI_REVIEW_REPO=https://gitlab.internal.company.com/bsp-tools/ai-code-review.git bash setup-ai-review.sh

repo forall -c 'git init && ai-review hook enable'
```
