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
项目使用 Python 3.10+。推荐在虚拟环境中安装依赖：
```bash
python -m venv .venv
source .venv/bin/activate  # Windows 使用 .venv\Scripts\activate
pip install -r requirements.txt
```
> 如果仓库尚未提供 `requirements.txt`，请根据自身环境安装 `openai`、`pydantic`、`typer` 等依赖，或使用 `pip install -e .` 安装自定义包。

### 3. 配置 OpenAI（可选）
若需启用 LLM 代理，请准备可用的 OpenAI API Key 并设置环境变量：
```bash
export OPENAI_API_KEY="sk-..."
```

## 运行模拟
使用命令行工具 `runner.py` 启动多局对战模拟：
```bash
python runner.py --games 100 --seed 42 --max-discards 5 --log out.jsonl
```

常用参数说明：
- `--games`：模拟的对局数。
- `--seed`：随机数种子，方便复现实验。
- `--max-discards`：允许弃牌的最大张数（默认 5）。
- `--model`：LLM 代理调用的模型名称（如 `gpt-4.1-mini`）。
- `--log`：保存结构化对局日志的文件路径。支持 JSON Lines 或 CSV。

当启用 LLM 代理时，系统会按 PRD 中约定的 JSON 契约与模型交互，并在解析失败时自动回退到保守策略。

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
- 新增自定义策略：实现 `agent_random.py` 中的接口即可接入。
- 替换日志管道：`logger.py` 支持结构化输出，可接入数据库或可视化工具。
- 批量实验：结合缓存、速率限制与 PRD 中的优化建议，构建大规模对战分析。

## 反馈与贡献
欢迎通过 Issue 或 Pull Request 分享你的改进意见或实验结果！如果你正在为课程、研究或项目做扩展，也欢迎在 PRD 中对需求进行补充。

祝你模拟愉快 🎲
