# Multi-Agent Five-Card Draw

欢迎来到 **Multi-Agent Five-Card Draw** 项目！该仓库提供了一个可复现的两人五张抽牌扑克模拟环境，支持基线随机策略与调用大语言模型（LLM）的智能体。你可以快速运行多局对战，观察不同策略的胜率、弃牌习惯以及最终牌型分布。

如果你对项目的完整需求、边界条件和实现规划感兴趣，请查看详细的产品需求文档：[PRD.md](./PRD.md)。

## 功能亮点

- 🎴 **真实的五张抽牌规则**：标准 52 张牌、一次性弃换、涵盖顺子/同花/葫芦等所有牌型判定与比较。
- 🤖 **多智能体对战**：内置随机策略代理和可调用 OpenAI API 的 LLM 代理，方便扩展自定义策略。
- 📊 **结构化日志与统计**：自动输出每局对战日志，并汇总胜率、弃牌次数、牌型分布等指标。
- 🧪 **完备的单元测试**：针对手牌评估的核心逻辑提供了覆盖边界情况的测试，保证比较结果可靠。

## 快速开始

### 1. 克隆项目

```bash
git clone https://github.com/your-org/multi-agent-poker-games.git
cd multi-agent-poker-games
```

### 2. 安装依赖

项目使用 Python 3.10+。推荐使用 [uv](https://github.com/astral-sh/uv) 管理虚拟环境与依赖：

```bash
uv venv
source .venv/bin/activate  # Windows 使用 .venv\Scripts\activate
uv pip install -r requirements.txt
```

若仓库尚未提供 `requirements.txt`，可直接安装关键依赖：

```bash
uv pip install "openai>=1.14" pydantic typer
```

（如更习惯传统 `python -m venv`/`pip` 流程，也可继续沿用。）

### 3. 配置 Azure OpenAI（启用 LLM 必需）

LLM 代理现在通过 Azure OpenAI 接入，请在运行前设置以下环境变量：

- `AZURE_OPENAI_API_KEY`：Azure OpenAI 密钥。
- `AZURE_OPENAI_ENDPOINT`：资源端点，例如 `https://your-resource.openai.azure.com/`。
- `AZURE_OPENAI_DEPLOYMENT_NAME`：部署名称，默认 `gpt-4o-new`。
- `AZURE_OPENAI_MODEL`：模型别名，默认 `azure_openai:gpt-4o`。
- `OPENAI_API_VERSION`：API 版本，默认 `2025-01-01-preview`。

**Linux/macOS：**

```bash
export AZURE_OPENAI_API_KEY="<your-key>"
export AZURE_OPENAI_ENDPOINT="https://your-resource.openai.azure.com/"
export AZURE_OPENAI_DEPLOYMENT_NAME="gpt-4o-new"      # 可自定义
export AZURE_OPENAI_MODEL="azure_openai:gpt-4o"       # 可自定义
export OPENAI_API_VERSION="2025-01-01-preview"        # 可自定义
```

**Windows PowerShell：**

```powershell
$env:AZURE_OPENAI_API_KEY="<your-key>"
$env:AZURE_OPENAI_ENDPOINT="https://your-resource.openai.azure.com/"
$env:AZURE_OPENAI_DEPLOYMENT_NAME="gpt-4o-new"
$env:AZURE_OPENAI_MODEL="azure_openai:gpt-4o"
$env:OPENAI_API_VERSION="2025-01-01-preview"
```

**Windows 命令提示符：**

```cmd
set AZURE_OPENAI_API_KEY=<your-key>
set AZURE_OPENAI_ENDPOINT=https://your-resource.openai.azure.com/
set AZURE_OPENAI_DEPLOYMENT_NAME=gpt-4o-new
set AZURE_OPENAI_MODEL=azure_openai:gpt-4o
set OPENAI_API_VERSION=2025-01-01-preview
```

建议将实际密钥保存在 `.env` 文件，并使用 `direnv` 或 `python-dotenv` 在本地加载，同时确保 `.env` 已添加到 `.gitignore` 以避免泄露。

## 运行模拟

使用命令行工具 `runner.py` 启动多局对战模拟：

```bash
python runner.py --agents alice:llm,bob:random,charlie:random --games 10 --seed 42 --funds 600,400,400 --min-bet 20 --log out.jsonl
```

五座位混合示例（两名 LLM 使用推理下注、两名随机、另一名使用 heuristic 下注）：

```bash
python runner.py --agents alice:llm:llm,bob:random,charlie:llm:heuristic,dana:random,erin:llm:llm \
    --bet-mode heuristic --games 10 --seed 7 --funds 600,400,400,300,500 --min-bet 50
```

若调用失败，可执行诊断脚本查看环境配置与 API 错误：

```bash
python scripts/check_azure_openai.py
```

### ⚠️ 运行提示

**没有完整设置 Azure 环境变量时：**

- 程序会检测到缺失的密钥或端点并打印提示
- LLM 代理将自动回退到保守策略
- `llm_metrics.api_calls` 为 0，`fallbacks` 等于游戏局数

**密钥有效但 Azure 资源无额度时：**

- Azure OpenAI 会返回配额错误
- 程序会输出指导信息并回退到保守策略

**密钥与额度均可用时：**

- CLI 将显示所用部署和模型映射
- 输出统计中会记录真实的 API 调用次数与缓存命中率

### 参数说明

- `--games`：模拟的对局数。
- `--seed`：随机数种子，方便复现实验。
- `--agents`：逗号分隔的座位定义，可用 `name:type[:bet]` 指定玩家、类型（`random` / `llm`）与下注模式（`heuristic` / `llm`）。
- `--initial-funds` / `--funds`：初始资金配置，支持为每个座位单独指定金额。
- `--bet-mode` / `--bet-modes`：控制 LLM 座位的下注策略，默认 `heuristic`，可通过列表或 `--agents` 中的 `:bet` 覆写。
- `--max-discards`：允许弃牌的最大张数（默认 5）。
- `--min-bet` / `--ante`：下注最小额与前注设置。
- `--max-raises`：单轮允许加注的次数上限。
- `--model`：Azure 部署名称（默认读取 `AZURE_OPENAI_DEPLOYMENT_NAME`）。
- `--log`：保存结构化对局日志的文件路径。支持 JSON Lines 或 CSV。

当启用 LLM 代理时，系统会按 PRD 中约定的 JSON 契约与模型交互，并在解析失败时自动回退到保守策略。

多智能体模式会自动维护每位玩家的资金以及下注逻辑，并在汇总中给出最终资金及盈亏变化：所有座位按顺序行动，在无人下注时可以选择 `check` 或 `bet`，一旦出现下注，后续玩家需要在 `call`、`raise`、`fold` 中做出选择。未弃牌的玩家完成换牌后比较牌力，赢家分享彩池并更新资金。对 LLM 座位，可选择 `heuristic` 模式使用内置下注策略，或 `llm` 模式让 Azure OpenAI 直接推理下注动作（缺少 API 时会自动回退到 heuristic）。

### 🔧 常见问题排查

**API连接问题：**
- 如遇到"Connection error"，请检查网络代理设置
- Windows设置代理：`$env:HTTP_PROXY="http://127.0.0.1:7890"`
- 确保代理软件已启动并允许程序访问OpenAI域名

**API配额问题：**
- ⚠️ **重要**：OpenAI API现在需要添加付费方式才能使用，即使是免费额度
- 如遇到"insufficient_quota"错误，需要：
  1. 访问 [OpenAI Billing页面](https://platform.openai.com/account/billing/overview)
  2. 添加有效的付费方式（信用卡/借记卡）
  3. 设置使用限额（可以设置很低的金额，如$5）
- 访问 [OpenAI Usage页面](https://platform.openai.com/usage) 查看配额使用情况
- 即使显示有预算余额，没有付费方式也无法调用API

**无付费方式的替代方案：**
- 程序会自动回退到保守策略，仍然可以进行随机代理 vs 保守策略的对战
- 保守策略会保留现有的对子，丢弃散牌，这比完全随机策略更合理

## 查看输出

- **命令行摘要**：每局对战的胜负情况、最终手牌和局部统计会实时打印。
- **日志文件**：包含完整的起手、弃牌、补牌和摊牌信息，可用于分析模型行为。
- **聚合统计**：程序会汇总胜率、平均弃牌数、牌型分布等指标，帮助评估策略表现。

## 运行测试

运行单元测试验证牌型评估逻辑：

```bash
pytest
```

## 扩展方向

- 实现多个agent的系统
- 实现每个agent可以选择是否是random或者LLM
- 采用next.js框架可视化结果：`logger.py` 支持结构化输出，可接入数据库或可视化工具。
- 实现可视化界面后，允许玩家接入next.js实现的web端游戏进行游玩。
- 初始化资金且允许下注：每个agent有可调整的初始资金，每一轮游戏按照agent序号顺序进行check or bet，一旦有一个agent做出了bet，下一位agent应该选择call，raise，fold中的一个选择，一轮游戏结束后，还处于游戏的玩家应该可以discard或者不换牌，直到有agent赢得了pot中所有的筹码。

## 反馈与贡献

欢迎通过 Issue 或 Pull Request 分享你的改进意见或实验结果！如果你正在为课程、研究或项目做扩展，也欢迎在 PRD 中对需求进行补充。

祝你模拟愉快 🎲
