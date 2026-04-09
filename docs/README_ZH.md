# Phantom — BitGN PAC1 挑战赛自主代理

基于 [OpenAI Agents SDK](https://github.com/openai/openai-agents-python) 构建的自主文件系统代理，用于解决 [BitGN PAC1 挑战赛](https://bitgn.com/challenge/PAC) — 一个在隔离虚拟环境中运行的 AI 代理基准测试。

**当前得分：~86%（37/43 个任务）**

![仪表板 — 任务结果](../assets/dashboard-tasks.jpg)

![仪表板 — 热力图对比](../assets/dashboard-heatmap.jpg)

## 什么是 PAC1？

[BitGN](https://bitgn.com) 运营代理基准测试，自主代理在隔离的沙盒虚拟机中解决实际任务。每个任务为代理提供一个文件系统工作空间和一条自然语言指令。代理必须自主探索、推理和执行——无需人工干预。

![BitGN 平台](../assets/bitgn-platform.png)

PAC1 包含 43 个任务：
- **CRM 操作** — 查找联系人、发送电子邮件、处理发票
- **知识管理** — 捕获、提炼、清理
- **收件箱处理** — 包含提示注入陷阱和 OTP 验证
- **安全** — 检测和拒绝恶意请求

了解更多：[bitgn.com/challenge/PAC](https://bitgn.com/challenge/PAC)

## 架构

```
用户任务 → LLM 分类器（选择技能）→ 代理（系统提示 + 技能提示 + 任务）
  → ReAct 循环：LLM → 工具调用 → 结果 → LLM → ... → report_completion
```

- **12 个专业技能**，支持热重载（编辑 `.md` 文件无需重启）
- **双重分类器** — 先 LLM，后正则表达式回退和覆盖逻辑
- **自我纠错代理** — 可在任务执行中调用 `list_skills` / `get_skill_instructions` 切换工作流
- **自动引用** — 跟踪已读/已写文件，自动注入 grounding_refs
- **空响应重试** — 模型返回纯文本而非工具调用时最多重试 3 次
- **实时仪表板** — React + Vite，SSE 流式传输，热力图对比，token 统计

## 快速开始

### 前提条件

- Python 3.12+
- [uv](https://docs.astral.sh/uv/) 包管理器
- Node.js 18+（用于仪表板）
- OpenAI 兼容的 LLM 端点
- [BitGN API 密钥](https://bitgn.com)

### 1. 安装依赖

```bash
cd pac1-py
uv sync
cd dashboard && npm install && cd ..
```

### 2. 设置环境变量

```bash
export OPENAI_API_KEY=<你的LLM密钥>
export OPENAI_BASE_URL=<你的LLM端点>
export MODEL_ID=<模型名称>
export BITGN_API_KEY=<你的BitGN密钥>
```

### 3. 启动（带仪表板）

```bash
# 终端 1 — 后端
cd pac1-py
uv run python server.py

# 终端 2 — 前端
cd pac1-py/dashboard
npm run dev
```

打开 **http://localhost:5173**，点击 **Run**。

### 4. 无头模式（仅 CLI）

```bash
cd pac1-py
uv run python main_v2.py
```

## 基于

本项目基于 [BitGN sample-agent](https://github.com/bitgn/sample-agent) 开发。

## 许可证

MIT
