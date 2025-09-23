"""Command-line interface for running multi-game simulations."""

from __future__ import annotations

import argparse
import importlib.util
import json
import random
from collections import Counter
from typing import Any, Dict, Optional

import os

from agent_llm import DEFAULT_DEPLOYMENT_NAME, DEFAULT_MODEL_ID, LLMAgent
from agent_random import RandomAgent
from engine import FiveCardDrawEngine, GameResult
from game_types import DecisionRules
from logger import GameLogger


def _load_config(path: str) -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8") as handle:
        if path.endswith((".yaml", ".yml")):
            spec = importlib.util.find_spec("yaml")
            if spec is None:
                raise RuntimeError("PyYAML is required to load YAML configurations")
            module = importlib.util.module_from_spec(spec)
            if spec.loader is None:  # pragma: no cover - defensive
                raise RuntimeError("Unable to import yaml module")
            spec.loader.exec_module(module)  # type: ignore[no-untyped-call]
            return module.safe_load(handle)  # type: ignore[attr-defined]
        return json.load(handle)


class StatsCollector:
    def __init__(self) -> None:
        self.total_games = 0
        self.draws = 0
        self.wins = [0, 0]
        self.discard_counts = [0, 0]
        self.rank_before = [Counter(), Counter()]
        self.rank_after = [Counter(), Counter()]
        self.improvements = [0, 0]

    def update(self, result: GameResult) -> None:
        self.total_games += 1
        if result.winner is None:
            self.draws += 1
        else:
            self.wins[result.winner] += 1
        for idx, player in enumerate(result.players):
            self.discard_counts[idx] += len(player.decision.discard_indices)
            self.rank_before[idx][player.initial_eval.rank_name] += 1
            self.rank_after[idx][player.final_eval.rank_name] += 1
            if player.final_eval.rank_id > player.initial_eval.rank_id:
                self.improvements[idx] += 1

    def summary(self, llm_metrics: Dict[str, float]) -> Dict[str, Any]:
        total = max(self.total_games, 1)
        win_rate_random = self.wins[0] / total
        win_rate_llm = self.wins[1] / total
        metrics = dict(llm_metrics)
        if self.total_games:
            metrics["api_calls_per_game"] = (
                llm_metrics.get("api_calls", 0.0) / self.total_games
            )
        summary = {
            "total_games": self.total_games,
            "wins": {
                "random": self.wins[0],
                "llm": self.wins[1],
                "draws": self.draws,
                "random_win_rate": win_rate_random,
                "llm_win_rate": win_rate_llm,
                "draw_rate": self.draws / total,
            },
            "average_discards": {
                "random": self.discard_counts[0] / total,
                "llm": self.discard_counts[1] / total,
            },
            "hand_type_distribution": {
                "random": {
                    "initial": self._distribution(self.rank_before[0], total),
                    "final": self._distribution(self.rank_after[0], total),
                },
                "llm": {
                    "initial": self._distribution(self.rank_before[1], total),
                    "final": self._distribution(self.rank_after[1], total),
                },
            },
            "improvement_rate": {
                "random": self.improvements[0] / total,
                "llm": self.improvements[1] / total,
            },
            "llm_metrics": metrics,
        }
        return summary

    @staticmethod
    def _distribution(counter: Counter, total: int) -> Dict[str, Dict[str, float]]:
        result: Dict[str, Dict[str, float]] = {}
        for name, count in counter.items():
            result[name] = {
                "count": int(count),
                "rate": (count / total) if total else 0.0,
            }
        return result


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Simulate multi-agent Five-card draw")
    parser.add_argument("--games", type=int, default=1, help="Number of games to simulate")
    parser.add_argument("--seed", type=int, default=None, help="RNG seed")
    parser.add_argument("--log", type=str, default=None, help="Path to write per-game logs")
    parser.add_argument(
        "--log-format", choices=["jsonl", "csv"], default="jsonl", help="Log format"
    )
    parser.add_argument(
        "--model",
        type=str,
        default=os.environ.get("AZURE_OPENAI_DEPLOYMENT_NAME", DEFAULT_DEPLOYMENT_NAME),
        help="Azure OpenAI deployment name",
    )
    parser.add_argument(
        "--temperature", type=float, default=0.0, help="LLM sampling temperature"
    )
    parser.add_argument(
        "--max-discards",
        type=int,
        default=5,
        help="Maximum number of cards a player may discard",
    )
    parser.add_argument("--cache-path", type=str, default=None, help="Path to LLM cache")
    parser.add_argument(
        "--config",
        type=str,
        default=None,
        help="Optional JSON or YAML configuration file",
    )
    parser.add_argument(
        "--rate-limit",
        type=float,
        default=None,
        help="Optional rate limit hint (requests per minute)",
    )
    return parser


def main(argv: Optional[list[str]] = None) -> None:
    parser = build_parser()
    defaults = parser.parse_args([])
    args = parser.parse_args(argv)
    if args.config:
        config = _load_config(args.config)
        for key, value in config.items():
            if hasattr(args, key) and getattr(args, key) == getattr(defaults, key):
                setattr(args, key, value)

    rng = random.Random(args.seed)
    agent_random = RandomAgent()
    agent_llm = LLMAgent(
        model=args.model,
        temperature=args.temperature,
        cache_path=args.cache_path,
    )

    model_alias = os.environ.get("AZURE_OPENAI_MODEL", DEFAULT_MODEL_ID)
    print(f"✅ Azure OpenAI 部署 `{args.model}` 已配置，模型映射 `{model_alias}`")
    print("🤖 开始运行 随机代理 vs LLM智能代理 对战...")
    print(f"🎮 总共进行 {args.games} 局游戏\n")
    
    engine = FiveCardDrawEngine(agent_random, agent_llm, rng=rng)
    logger: Optional[GameLogger] = None
    if args.log:
        logger = GameLogger(args.log, fmt=args.log_format)

    stats = StatsCollector()
    rules = DecisionRules(max_discards=args.max_discards)
    for game_id in range(1, args.games + 1):
        result = engine.play_game(game_id, rules)
        if logger:
            logger.log(result)
        stats.update(result)

    if logger:
        logger.close()
    agent_llm.flush_cache()
    summary = stats.summary(agent_llm.metrics())
    
    # 输出结果提示
    llm_metrics = agent_llm.metrics()
    api_calls = llm_metrics.get("api_calls", 0)
    fallbacks = llm_metrics.get("fallbacks", 0)
    
    print("\n" + "="*50)
    print("🏁 游戏结束统计:")
    if api_calls > 0:
        print(f"✅ LLM API 调用次数: {api_calls}")
        print(f"📈 缓存命中率: {llm_metrics.get('cache_hit_rate', 0):.2%}")
        if fallbacks > 0:
            print(f"⚠️  回退到保守策略次数: {fallbacks}")
    else:
        print("🔒 未使用 LLM API (全部使用保守策略回退)")
    print("="*50 + "\n")
    
    print(json.dumps(summary, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
