# PRD：Two-Player Five-Card Draw（Multi-Agent，LLM 决策版）
1. 目标与范围

模拟两名玩家进行 Five-card draw 一局或多局对战。

Agent1：基线随机策略（仅在换牌阶段做随机弃换 0–3 张）。

Agent2：通过 OpenAI API 的大模型做出“换哪些牌”的决策（无下注环节）。

输出每局对战日志与多局统计（胜率、平均换牌数、牌型分布）。

不做：下注/筹码系统、多人博弈、联机/GUI、策略可插拔框架。

2. 用户故事

研究/教学：比较“随机 vs LLM”在 Five-card draw 的长期胜率差异与牌型提升能力。

工程：通过清晰的 JSON 决策契约，稳定复现 LLM 的换牌动作并可批量模拟。

3. 核心玩法规则（简化版，无下注）

发牌：标准 52 张牌，洗牌后每人发 5 张。

换牌阶段：玩家可弃 0–5 张并等量补牌（一次性完成）。

摊牌：按牌型比大小：
高牌 < 一对 < 两对 < 三条 < 顺子 < 同花 < 葫芦 < 四条 < 同花顺。
顺子 A 可作高（10-J-Q-K-A）或低（A-2-3-4-5）。

胜负：比较牌型；如同牌型则按主值/踢脚（kicker）逐级比较；完全相同则平局。

4. 系统组成

deck.py：牌堆/洗牌/发牌。

hand_eval.py：五张牌型评估与比较器（返回 (rank_id, tiebreak_tuple)）。

agent_random.py：Agent1 随机策略。

agent_llm.py：Agent2（OpenAI API 调用 + JSON 决策解析）。

engine.py：回合管理（发牌→两名玩家依次决策→补牌→摊牌→记账）。

runner.py：CLI 批量模拟与统计输出（CSV/JSON 日志）。

logger.py：结构化日志（每局手牌、换牌选择、最终牌型/胜负）。

5. Agent2（OpenAI API）决策契约
5.1 决策输入（Engine → LLM）

可见信息：自己的 5 张手牌（带花色与点数）、换牌规则约束（0–5 张）、禁止“未揭示信息”（看不到牌堆/对手手牌）。

目标：最大化最终牌型强度。

输出格式：严格 JSON，仅给出要弃掉的索引数组（基于当前 5 张手牌的 0-based 索引），以及可选的“理由”。

示例输入（user 内容）：

{
  "hand": ["AS","KH","KD","7C","2D"],
  "rules": {"max_discards": 5},
  "task": "Return indices of cards to discard (0-4)."
}

5.2 决策输出（LLM → Engine）
{
  "discard_indices": [0, 3, 4],
  "rationale": "Keep the KK pair; replace A,7,2 to improve to two-pair/trips/full house."
}

5.3 模型与参数（建议）

模型：gpt-4.1-mini 或更高性价比支持 JSON 输出的模型（你可以替换为你账户中可用的、支持 response_format 的最新模型）。

temperature: 0（稳定可复现）。

response_format: {"type":"json_schema","json_schema":{...}}（强约束输出，避免解析失败）。

重试：网络/速率限制/解析错误时 2–3 次指数退避重试。

超时：2–5s / 调用；解析失败则本局回退为“保守策略”（例如保留已成对的牌，其他全换，最多 3 张）。

成本提示：一次对局仅 1 次 LLM 调用（Agent2 的换牌决策），批量 100k 局成本可控但需缓存/去重（见 §9）。

5.4 提示词模板（建议）

system

You are a poker assistant playing Five-card draw. 
Rules: one draw round; you may discard 0-5 cards once; unknown cards are uniformly random.
Goal: maximize final 5-card hand strength.
Output strictly in the required JSON schema. No extra text.


user（见 5.1 示例）

json schema（关键片段）

{
  "name": "DiscardDecision",
  "schema": {
    "type": "object",
    "properties": {
      "discard_indices": {
        "type": "array",
        "items": {"type": "integer", "minimum": 0, "maximum": 4},
        "minItems": 0,
        "maxItems": 5
      },
      "rationale": {"type": "string"}
    },
    "required": ["discard_indices"],
    "additionalProperties": false
  }
}

6. 评估与日志

逐局日志（CSV/JSON）：
game_id, p1_hand_before, p1_discards, p1_hand_after, p1_rank, p2_hand_before, p2_discards, p2_hand_after, p2_rank, winner

聚合指标：

胜率/和局率；

平均弃牌数；

牌型分布（起手 vs 摊牌）；

牌型提升率（起手→摊牌 Rank 改善的比例，按玩家统计）。

健全性检查：

LLM 输出可解析且索引合法；

不允许重复/越界弃牌；

随机数种子记录（重现实验）。

7. 边界与规则细节

顺子低 A：A-2-3-4-5（花色任意）；

同花顺判定先同花后顺子；

平局判定：按牌型主次关键值逐层比较（例：对子比对点数，再比三张/两对的高对、低对，再比踢脚）；完全相同判平。

8. CLI 与配置

命令：python runner.py --games 10000 --seed 42 --log out.jsonl --model gpt-4.1-mini --rate-limit 60

环境变量：OPENAI_API_KEY

配置文件（YAML/JSON）：模型名、温度、并发、重试、超时、是否开启等价手缓存（见 §9）。

9. 性能与成本控制

等价手缓存：将“等价手牌 canonical 表示（按点数归一、花色型归一） + 决策规则/模型名”作为 key，缓存 LLM 的 discard_indices。大量随机对局中会频繁命中等价模式，可显著降低 API 次数。

批处理：可将多局请求串行化并控并发，遵守速率限制（如 60 RPM）。

短输出：仅 JSON、禁用赘述，减少 token。

降级路径：解析失败或超时，落到“简单规则”决定弃牌，保证流水线不中断。

10. 验收标准（DoD）

 单局可运行并打印双方起手、弃换与最终牌型，胜负正确。

 1 万局模拟在单机可完成，日志完整、无解析异常中断。

 评估统计输出胜率、牌型分布与提升率；LLM 决策 JSON 合法率 ≥ 99.5%。

 顺子、同花、葫芦、同花顺等边界牌型及平局比较通过单元测试（≥ 50 个用例）。

 缓存命中率报告与成本估算（调用次数/局）。

11. 风险与对策

LLM 偶发输出不合规 → 使用 response_format: json_schema + 严格解析 + 重试 + 降级策略。

成本超预算 → 开启等价手缓存；用更经济的模型；降低对局数或抽样评测。

随机性导致波动 → 固定 RNG 种子；对比统计使用置信区间（Wilson/正态近似）。
