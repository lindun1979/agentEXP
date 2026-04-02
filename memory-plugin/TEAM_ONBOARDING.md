# Team Onboarding（5分钟接入）

适用对象：希望在自己的 OpenClaw 环境中接入 `agentEXP` 记忆插件的同事。

---

## 1) 克隆仓库

```bash
git clone https://github.com/lindun1979/agentEXP.git
cd agentEXP/memory-plugin
```

## 2) 安装配置

```bash
bash install.sh
```

安装脚本会把 3 个配置文件复制到：

- `~/.openclaw/memory/chinese_rewrite_map.json`
- `~/.openclaw/memory/noise_intent_patterns.json`
- `~/.openclaw/memory/hybrid_search_config.json`

## 3) 环境检查（必须）

```bash
command -v qmd
python3 --version
ls -la ~/.openclaw/memory/
```

判定标准：
- `qmd` 有路径输出
- Python 可用
- 上述 3 个 json 文件存在

## 4) 最小验证（推荐）

在 Python 里执行：

```python
from hybrid_memory_adapter import HybridMemoryAdapter
adapter = HybridMemoryAdapter(agent="main")
print(adapter.search("STATE 下一步"))
```

预期：
- 返回一个字典
- `is_noise` 为 `False`
- `results` 至少有可解析结构（为空也不报错）

## 5) OpCoder 节点接入（可选）

```python
from hybrid_memory_adapter import HybridMemoryAdapter
adapter = HybridMemoryAdapter(agent="OpCoder")
```

用于读取 `OpCoder` 对应的 qmd 配置与缓存目录。

---

## 常见问题排查

### A. `command not found: qmd`
原因：qmd 未安装或不在 PATH。
处理：先安装 qmd，再重新打开 shell；确认 `command -v qmd` 有输出。

### B. `配置文件未找到`
原因：未执行 `install.sh` 或复制路径不对。
处理：重新执行 `bash install.sh`，并检查 `~/.openclaw/memory/*.json`。

### C. 检索总是空结果
可能原因：
1. 查询命中不到内容（正常）
2. qmd 索引/目录配置不完整
3. noise 规则把查询短路了

处理顺序：
1) 用明显记忆类查询（如 `MEMORY.md`、`STATE Next`）
2) 检查 `noise_intent_patterns.json` 是否误拦截
3) 单独运行 qmd 检索命令验证底层：

```bash
qmd search "STATE Next" --json -n 3 -c memory-dir-main
```

### D. `vsearch` 慢或失败
说明：当前策略是 `search` 优先，`vsearch` 兜底；慢时可先关闭兜底做排查。
可在 `hybrid_search_config.json` 中临时设置：

```json
{
  "fallback_to_vsearch": false
}
```

---

## 升级方式

```bash
cd agentEXP
git pull
cd memory-plugin
bash install.sh
```

升级后建议做一次第 4 节最小验证。

---

## 版本信息

- 初始发布提交：`7187199`
- 文档：`TEAM_ONBOARDING.md`
