# AI Code Review — 安裝與使用 SOP

## 一、安裝 SOP

### 前置需求

| 項目 | 需求 | 確認指令 |
|------|------|----------|
| Python | 3.10 以上 | `python3 --version` |
| Git | 任意版本 | `git --version` |
| pip | 任意版本 | `pip --version` |
| Ollama（選用） | 本地 LLM 推理 | `ollama --version` |

### Step 1：安裝 ai-review

```bash
pip install ai-code-review
```

如果是從原始碼安裝：

```bash
git clone https://github.com/seen0722/ai-code-review.git
cd ai-code-review
pip install .
```

安裝完成後驗證：

```bash
ai-review --help
```

預期輸出：

```
Usage: ai-review [OPTIONS] COMMAND [ARGS]...

  AI-powered code review for Android BSP teams.

Options:
  --provider TEXT                 LLM provider (ollama/openai/enterprise)
  --model TEXT                    Model name
  --format [terminal|markdown|json]
  --help                         Show this message and exit.

Commands:
  check-commit  Check commit message format and optionally improve with AI.
  config        Manage configuration.
  hook          Manage git hooks (global or per-repo).
```

### Step 2：設定 LLM Provider

依據環境選擇一種：

#### 方案 A：本地 Ollama（推薦內網使用）

```bash
# 1. 安裝 Ollama（若未安裝）
curl -fsSL https://ollama.com/install.sh | sh

# 2. 下載模型
ollama pull llama3.1

# 3. 啟動 Ollama 服務
ollama serve &

# 4. 設定 ai-review
ai-review config set provider default ollama
ai-review config set ollama base_url http://localhost:11434
ai-review config set ollama model llama3.1
```

#### 方案 B：企業內部 LLM

```bash
ai-review config set provider default enterprise
ai-review config set enterprise base_url https://llm.internal.company.com
ai-review config set enterprise api_path /v1/chat/completions
ai-review config set enterprise model internal-codellama-70b
ai-review config set enterprise auth_type bearer
ai-review config set enterprise auth_token_env ENTERPRISE_LLM_KEY

# 設定環境變數（加到 ~/.bashrc 或 ~/.zshrc）
export ENTERPRISE_LLM_KEY="your-api-key-here"
```

#### 方案 C：OpenAI

```bash
ai-review config set provider default openai
ai-review config set openai api_key_env OPENAI_API_KEY
ai-review config set openai model gpt-4o

# 設定環境變數
export OPENAI_API_KEY="sk-..."
```

設定完成後驗證：

```bash
ai-review config get provider default
```

預期輸出：`ollama`（或 `enterprise` / `openai`）

### Step 3：啟用 Global Git Hooks

```bash
ai-review hook install --global
```

預期輸出：

```
  Created /home/user/.config/ai-code-review/hooks/pre-commit
  Created /home/user/.config/ai-code-review/hooks/commit-msg

Global hooks installed.
core.hooksPath → /home/user/.config/ai-code-review/hooks
Hooks only activate in repos with a .ai-review marker file.
Enable a repo: touch /path/to/repo/.ai-review
```

驗證：

```bash
ai-review hook status
```

預期輸出：

```
Global hooks:
  core.hooksPath = /home/user/.config/ai-code-review/hooks
  pre-commit: installed
  commit-msg: installed

Current repo hooks:
  pre-commit: not installed
  commit-msg: not installed
```

### Step 4：在需要的 Repo 啟用 AI Review

Global hooks 採用 **opt-in 機制** — 只有 repo 根目錄存在 `.ai-review` 標記檔的 repo 才會觸發 AI review，其他 repo 完全不受影響。

```bash
# 單一 repo 啟用
cd /path/to/camera-hal
touch .ai-review

# 批次啟用多個 repo
for repo in camera-hal kernel-bsp audio-driver display-drm; do
    touch /path/to/repos/$repo/.ai-review
done
```

驗證（在已啟用的 repo 中）：

```bash
cd /path/to/camera-hal
ls .ai-review    # 檔案存在即啟用
```

### Step 5（選用）：調整審查副檔名

預設只審查 `c, cpp, h, hpp, java`。如需調整：

```bash
# 加入 Kotlin
ai-review config set review include_extensions "c,cpp,h,hpp,java,kt"

# 審查所有檔案（設為空字串）
ai-review config set review include_extensions ""
```

### 安裝完成檢查清單

- [ ] `ai-review --help` 正常顯示
- [ ] `ai-review config get provider default` 顯示已設定的 provider
- [ ] `ai-review hook status` 顯示 global hooks installed
- [ ] 需要 AI review 的 repo 根目錄有 `.ai-review` 檔案
- [ ] （Ollama 用戶）`ollama list` 顯示已下載的模型

---

## 二、使用 SOP

### 場景 1：日常 Commit（自動觸發）

安裝 global hooks 並在 repo 中建立 `.ai-review` 標記檔後，每次 `git commit` 會自動執行兩道檢查。無需額外操作。

**前提**：repo 根目錄已有 `.ai-review` 檔案（`touch .ai-review`）。

#### 實例：修改 Camera HAL 並 commit

```bash
# 1. 修改程式碼
vim hardware/camera/CameraHal.cpp

# 2. Stage 變更
git add hardware/camera/CameraHal.cpp

# 3. Commit（hooks 自動觸發）
git commit -m "[CAM-456] fix null pointer crash when switching camera"
```

**Hook 執行流程：**

```
git commit
  │
  ├─ 檢查 .ai-review 標記檔
  │   ✗ 不存在 → 跳過所有 hook，直接 commit
  │   ✓ 存在 → 繼續執行
  │
  ├─ [Hook 1] AI Code Review (pre-commit stage)
  │   分析 CameraHal.cpp 的 diff（只審查 c/cpp/h/hpp/java）...
  │
  │   情況 A — 無嚴重問題：
  │   ✅ Passed
  │
  │   情況 B — 發現嚴重問題：
  │   🔍 AI Code Review — 2 issue(s) found
  │     ❌ CameraHal.cpp:142
  │        Memory leak: allocateBuffer() without matching freeBuffer()
  │     ⚠️ CameraHal.cpp:89
  │        Potential null pointer dereference on mDevice
  │   ❌ Commit blocked (critical/error found)
  │   → commit 被擋下，需修復後重新 commit
  │
  ├─ [Hook 2] Commit Message Check (commit-msg stage)
  │   ✅ Commit message format OK.
  │   Original:  [CAM-456] fix null pointer crash when switching camera
  │   Suggested: [CAM-456] Fix null pointer crash during camera switch.
  │   (non-interactive: auto-accept)
  │   ✅ Commit message updated.
  │
  └─ ✅ Commit 成功
```

#### 實例：commit message 格式錯誤

```bash
git commit -m "fix camera bug"
```

輸出：

```
Commit message must match: [PROJECT-NUMBER] description
Example: [BSP-123] fix camera HAL crash on boot
```

commit 被擋下。修正後重新 commit：

```bash
git commit -m "[CAM-456] fix camera bug"
```

### 場景 2：手動執行 Code Review

不透過 hook，手動對 staged 變更執行審查。

```bash
# Stage 檔案
git add kernel/drivers/gpu/drm/panel-samsung.c

# 執行 review
ai-review
```

輸出範例：

```
🔍 AI Code Review — 1 issue(s) found

  ❌ panel-samsung.c:234
     Buffer overflow: memcpy size exceeds destination buffer

──────────────────────────────────────────────────
Summary: 1 error
❌ Commit blocked (critical/error found)
```

#### 指定輸出格式

```bash
# Markdown（適合貼到 Issue 或文件）
ai-review --format markdown
```

輸出：

```markdown
# AI Code Review

| Severity | File | Line | Issue |
|----------|------|------|-------|
| error | panel-samsung.c | 234 | Buffer overflow: memcpy size exceeds destination buffer |

**Summary:** 1 error
**Status:** ❌ Blocked
```

```bash
# JSON（適合 CI/CD 或腳本整合）
ai-review --format json
```

輸出：

```json
{
  "issues": [
    {
      "severity": "error",
      "file": "panel-samsung.c",
      "line": 234,
      "message": "Buffer overflow: memcpy size exceeds destination buffer"
    }
  ],
  "summary": "1 error",
  "blocked": true
}
```

### 場景 3：手動檢查 Commit Message

```bash
# 檢查格式是否正確
echo "[BSP-789] update device tree for display" | ai-review check-commit

# 帶 AI 改善（指定檔案）
echo "[BSP-789] update device tree for display" > /tmp/msg
ai-review check-commit /tmp/msg
```

### 場景 4：臨時跳過 Hooks

```bash
# 跳過所有 hooks（緊急修復時使用）
git commit --no-verify -m "[HOTFIX-001] emergency fix for boot loop"
```

### 場景 5：啟用或停用特定 Repo

```bash
# 啟用 AI review（建立標記檔）
cd /path/to/camera-hal
touch .ai-review

# 停用 AI review（移除標記檔）
rm .ai-review

# 批次啟用多個 repo
for repo in camera-hal kernel-bsp audio-driver; do
    touch /path/to/repos/$repo/.ai-review
done

# 批次停用
for repo in camera-hal kernel-bsp audio-driver; do
    rm -f /path/to/repos/$repo/.ai-review
done
```

沒有 `.ai-review` 標記檔的 repo，hooks 會自動跳過，commit 行為與未安裝 ai-review 完全相同。

---

## 三、設定參考

### 設定檔位置

```
~/.config/ai-code-review/config.toml
```

### 完整設定範例

```toml
[provider]
default = "ollama"

[ollama]
base_url = "http://localhost:11434"
model = "llama3.1"

[review]
include_extensions = "c,cpp,h,hpp,java"

# --- 以下為其他 provider 設定（未使用時可不填）---

[openai]
api_key_env = "OPENAI_API_KEY"
model = "gpt-4o"

[enterprise]
base_url = "https://llm.internal.company.com"
api_path = "/v1/chat/completions"
model = "internal-codellama-70b"
auth_type = "bearer"
auth_token_env = "ENTERPRISE_LLM_KEY"
```

### 審查嚴重等級

| 等級 | 說明 | 是否擋下 Commit |
|------|------|:---------------:|
| critical | 安全漏洞、資料洩漏 | **是** |
| error | 明顯 bug、邏輯錯誤 | **是** |
| warning | 潛在問題 | 否 |
| info | 一般建議 | 否 |

### 審查重點（BSP 導向）

AI 只聚焦以下嚴重問題，**不會**報告程式碼風格或命名建議：

- 記憶體洩漏（malloc/free 不匹配）
- Null pointer 解引用
- Race condition（多執行緒競爭）
- Hardcoded 密碼/金鑰
- Buffer overflow
- 資源未釋放（file descriptor、socket 等）

---

## 四、常見問題

### Q: 安裝後所有 repo 都會被影響嗎？

不會。Global hooks 採用 **opt-in 機制**，只有 repo 根目錄存在 `.ai-review` 檔案的 repo 才會觸發 AI review。沒有標記檔的 repo 完全不受影響，commit 行為與未安裝 ai-review 時相同。

```bash
# 啟用
touch /path/to/repo/.ai-review

# 停用
rm /path/to/repo/.ai-review
```

### Q: Ollama 服務沒啟動怎麼辦？

```bash
# 啟動服務
ollama serve &

# 確認運行中
curl http://localhost:11434/api/tags
```

### Q: 誤報太多怎麼辦？

小型模型（如 llama3.1:7b）可能產生誤報。建議：

1. 使用更大的模型：`ollama pull llama3.1:70b`
2. 或切換到 OpenAI GPT-4o
3. 單次跳過：`git commit --no-verify`

### Q: 如何更新 ai-review？

```bash
pip install --upgrade ai-code-review
```

### Q: 如何完全移除？

```bash
# 1. 移除 global hooks
ai-review hook uninstall --global

# 2. 移除所有 repo 的標記檔
find /path/to/repos -name ".ai-review" -delete

# 3. 移除套件
pip uninstall ai-code-review

# 4. 移除設定檔（選用）
rm -rf ~/.config/ai-code-review
```

### Q: 可以多人共用同一台 Ollama 嗎？

可以。在一台伺服器上啟動 Ollama，其他人設定 `base_url` 指向該伺服器：

```bash
ai-review config set ollama base_url http://192.168.1.100:11434
```

---

## 五、快速安裝腳本

將以下腳本存為 `setup-ai-review.sh`，發給團隊成員執行：

```bash
#!/usr/bin/env bash
set -e

echo "=== AI Code Review Setup ==="

# 1. Install
pip install ai-code-review

# 2. Configure Ollama provider
ai-review config set provider default ollama
ai-review config set ollama base_url "${OLLAMA_URL:-http://localhost:11434}"
ai-review config set ollama model "${OLLAMA_MODEL:-llama3.1}"

# 3. Enable global hooks (opt-in mode)
ai-review hook install --global

echo ""
echo "=== Setup Complete ==="
echo "Global hooks installed (opt-in mode)."
echo ""
echo "Enable AI review for a repo:"
echo "  touch /path/to/repo/.ai-review"
echo ""
echo "To skip once: git commit --no-verify"
```

使用方式：

```bash
# 使用預設 Ollama（localhost）
bash setup-ai-review.sh

# 指定共用 Ollama 伺服器
OLLAMA_URL=http://192.168.1.100:11434 bash setup-ai-review.sh

# 安裝後，在需要的 repo 啟用
touch /path/to/camera-hal/.ai-review
touch /path/to/kernel-bsp/.ai-review
```
