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

```bash
pip install ai-code-review
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

### 安裝檢查清單

- [ ] `ai-review --help` 正常顯示
- [ ] `ai-review config get provider default` 顯示已設定的 provider
- [ ] `ai-review hook status` 顯示 template hooks installed
- [ ] 需要 AI review 的 repo 已執行 `ai-review hook enable`

---

## 二、日常使用

### 自動觸發（推薦）

啟用後，`git commit` 自動執行：

```
git commit -m "[CAM-456] fix null pointer crash"
  |
  +-- 檢查 ai-review.enabled -- 未啟用則跳過
  |
  +-- [Hook 1] pre-commit: AI Code Review
  |   PASS  無嚴重問題 -- 繼續
  |   BLOCK 發現 critical/error -- 擋下 commit
  |
  +-- [Hook 2] commit-msg: 格式檢查 + AI 英文優化
  |   PASS  格式正確 -- AI 改善英文描述（自動接受）
  |   BLOCK 格式錯誤 -- 擋下 commit
  |
  +-- Commit 成功
```

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

### 手動 Code Review

```bash
git add kernel/drivers/gpu/drm/panel-samsung.c
ai-review                    # terminal 輸出
ai-review --format markdown  # Markdown（貼 Issue）
ai-review --format json      # JSON（CI/CD 整合）
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

[review]
include_extensions = "c,cpp,h,hpp,java"

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
echo "=== AI Code Review Setup ==="
pip install ai-code-review
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
# 使用
bash setup-ai-review.sh
repo forall -c 'git init && ai-review hook enable'
```
