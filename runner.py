"""Command-line interface for running multi-agent Five-card draw simulations."""

from __future__ import annotations

import argparse
import importlib.util
import json
import random
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Sequence

from agent_llm import LLMAgent
from agent_random import RandomAgent
from engine import FiveCardDrawEngine, GameResult, PlayerSeat
from game_types import DecisionRules
from logger import GameLogger


@dataclass
class AgentSpec:
    name: str
    kind: str
    bet_mode: str


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
    def __init__(self, seats: Sequence[PlayerSeat]) -> None:
        self.total_games = 0
        self.played_games = 0
        self.draws = 0
        self.total_pot = 0
        self.wins: Dict[int, int] = {seat.player_id: 0 for seat in seats}
        self.folds: Dict[int, int] = {seat.player_id: 0 for seat in seats}
        self.discards: Dict[int, int] = {seat.player_id: 0 for seat in seats}
        self.initial_bankrolls: Dict[int, int] = {
            seat.player_id: seat.stack for seat in seats
        }
        self.bankrolls: Dict[int, int] = dict(self.initial_bankrolls)

    def update(self, result: GameResult) -> None:
        self.total_games += 1
        if not result.players:
            self.bankrolls.update(result.bankrolls)
            return

        self.played_games += 1
        self.total_pot += result.pot
        if result.is_draw:
            self.draws += 1
        for winner in result.winners:
            self.wins[winner] = self.wins.get(winner, 0) + 1
        for player in result.players:
            if player.folded:
                self.folds[player.player_id] = self.folds.get(player.player_id, 0) + 1
            self.discards[player.player_id] = (
                self.discards.get(player.player_id, 0) + len(player.decision.discard_indices)
            )
        for pid, bankroll in result.bankrolls.items():
            self.bankrolls[pid] = bankroll

    def summary(
        self,
        seats: Sequence[PlayerSeat],
        llm_metrics: Dict[int, Dict[str, float]],
    ) -> Dict[str, Any]:
        playable = max(self.played_games, 1)
        player_rows: List[Dict[str, Any]] = []
        for seat in seats:
            pid = seat.player_id
            player_rows.append(
                {
                    "player_id": pid,
                    "name": seat.name,
                    "wins": self.wins.get(pid, 0),
                    "win_rate": self.wins.get(pid, 0) / playable,
                    "folds": self.folds.get(pid, 0),
                    "fold_rate": self.folds.get(pid, 0) / playable,
                    "avg_discards": self.discards.get(pid, 0) / playable,
                    "initial_bankroll": self.initial_bankrolls.get(pid, seat.stack),
                    "bankroll": self.bankrolls.get(pid, seat.stack),
                    "bankroll_change": self.bankrolls.get(pid, seat.stack)
                    - self.initial_bankrolls.get(pid, seat.stack),
                    "bet_mode": seat.agent.bet_mode if isinstance(seat.agent, LLMAgent) else "n/a",
                    "llm_metrics": llm_metrics.get(pid),
                }
            )
        return {
            "total_games": self.total_games,
            "games_played": self.played_games,
            "draws": self.draws,
            "total_pot": self.total_pot,
            "players": player_rows,
        }


def parse_agent_string(value: str, default_bet_mode: str) -> List[AgentSpec]:
    tokens = [token.strip() for token in value.split(",") if token.strip()]
    if len(tokens) < 2:
        raise ValueError("At least two agents are required")
    specs: List[AgentSpec] = []
    for idx, token in enumerate(tokens, start=1):
        parts = token.split(":")
        if len(parts) == 1:
            name = f"Player {idx}"
            kind = parts[0].strip().lower()
            bet_mode = default_bet_mode
        elif len(parts) == 2:
            name = parts[0].strip() or f"Player {idx}"
            kind = parts[1].strip().lower()
            bet_mode = default_bet_mode
        else:
            name = parts[0].strip() or f"Player {idx}"
            kind = parts[1].strip().lower()
            bet_mode = parts[2].strip().lower() or default_bet_mode
        if kind not in {"random", "llm"}:
            raise ValueError(f"Unsupported agent type: {kind}")
        if bet_mode not in {"heuristic", "llm"}:
            raise ValueError(f"Unsupported bet mode: {bet_mode}")
        specs.append(AgentSpec(name=name, kind=kind, bet_mode=bet_mode))
    return specs


def parse_funds(string: Optional[str], count: int, default: int) -> List[int]:
    if not string:
        return [default for _ in range(count)]
    parts = [part.strip() for part in string.split(",")]
    if len(parts) != count:
        raise ValueError("Number of funds must match number of agents")
    funds = []
    for part in parts:
        amount = int(part)
        if amount < 0:
            raise ValueError("Funds must be non-negative")
        funds.append(amount)
    return funds


def parse_bet_modes(
    string: Optional[str], count: int, default: str
) -> List[str]:
    if not string:
        return [default for _ in range(count)]
    parts = [part.strip().lower() for part in string.split(",")]
    if len(parts) != count:
        raise ValueError("Number of bet modes must match number of agents")
    modes: List[str] = []
    for part in parts:
        mode = part or default
        if mode not in {"heuristic", "llm"}:
            raise ValueError("Bet modes must be 'heuristic' or 'llm'")
        modes.append(mode)
    return modes


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Simulate multi-agent Five-card draw")
    parser.add_argument("--games", type=int, default=1, help="Number of games to simulate")
    parser.add_argument("--seed", type=int, default=None, help="RNG seed")
    parser.add_argument("--log", type=str, default=None, help="Path to write per-game logs")
    parser.add_argument(
        "--log-format", choices=["jsonl", "csv"], default="jsonl", help="Log format"
    )
    parser.add_argument(
        "--agents",
        type=str,
        default="random,llm",
        help="Comma-separated agent definitions (type or name:type)",
    )
    parser.add_argument(
        "--initial-funds",
        type=int,
        default=500,
        help="Initial bankroll for each agent when --funds is not provided",
    )
    parser.add_argument(
        "--funds",
        type=str,
        default=None,
        help="Comma-separated bankrolls matching --agents",
    )
    parser.add_argument(
        "--bet-mode",
        choices=["heuristic", "llm"],
        default="heuristic",
        help="Default betting strategy for LLM agents",
    )
    parser.add_argument(
        "--bet-modes",
        type=str,
        default=None,
        help="Comma-separated betting modes per agent (heuristic|llm)",
    )
    parser.add_argument(
        "--model",
        type=str,
        default="gpt-4o-new",
        help="Azure OpenAI deployment name for LLM agents",
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
    parser.add_argument(
        "--min-bet",
        type=int,
        default=10,
        help="Minimum bet/raise size during betting",
    )
    parser.add_argument(
        "--ante",
        type=int,
        default=0,
        help="Ante amount each player posts at the start of a game",
    )
    parser.add_argument(
        "--max-raises",
        type=int,
        default=3,
        help="Maximum number of raises allowed in a betting round",
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


def instantiate_agents(
    specs: Sequence[AgentSpec],
    funds: Sequence[int],
    *,
    model: str,
    temperature: float,
    cache_path: Optional[str],
) -> List[PlayerSeat]:
    seats: List[PlayerSeat] = []
    for idx, (spec, bankroll) in enumerate(zip(specs, funds)):
        if spec.kind == "random":
            agent = RandomAgent()
        else:
            agent = LLMAgent(
                model=model,
                temperature=temperature,
                cache_path=cache_path,
                bet_mode=spec.bet_mode,
            )
        seat = PlayerSeat(player_id=idx, name=spec.name, agent=agent, stack=bankroll)
        seats.append(seat)
    return seats


def collect_llm_metrics(seats: Sequence[PlayerSeat]) -> Dict[int, Dict[str, float]]:
    metrics: Dict[int, Dict[str, float]] = {}
    for seat in seats:
        if isinstance(seat.agent, LLMAgent):
            metrics[seat.player_id] = seat.agent.metrics()
    return metrics


def flush_llm_caches(seats: Sequence[PlayerSeat]) -> None:
    for seat in seats:
        if isinstance(seat.agent, LLMAgent):
            seat.agent.flush_cache()


def main(argv: Optional[List[str]] = None) -> None:
    parser = build_parser()
    defaults = parser.parse_args([])
    args = parser.parse_args(argv)
    if args.config:
        config = _load_config(args.config)
        for key, value in config.items():
            if hasattr(args, key) and getattr(args, key) == getattr(defaults, key):
                setattr(args, key, value)

    rng = random.Random(args.seed)
    agent_specs = parse_agent_string(args.agents, args.bet_mode)
    funds = parse_funds(args.funds, len(agent_specs), args.initial_funds)
    if args.bet_modes:
        bet_modes = parse_bet_modes(args.bet_modes, len(agent_specs), args.bet_mode)
        for spec, mode in zip(agent_specs, bet_modes):
            spec.bet_mode = mode
    seats = instantiate_agents(
        agent_specs,
        funds,
        model=args.model,
        temperature=args.temperature,
        cache_path=args.cache_path,
    )

    print("✅ 已配置座位:")
    for seat in seats:
        if isinstance(seat.agent, LLMAgent):
            role = f"LLM (bet:{seat.agent.bet_mode})"
        else:
            role = "Random"
        print(f"  - {seat.name} (#{seat.player_id + 1}, {role}), 初始资金 {seat.stack}")
    print(f"🎮 将进行 {args.games} 局游戏\n")

    engine = FiveCardDrawEngine(seats, rng=rng)
    logger: Optional[GameLogger] = None
    if args.log:
        logger = GameLogger(args.log, fmt=args.log_format)

    stats = StatsCollector(seats)
    rules = DecisionRules(
        max_discards=args.max_discards,
        min_bet=args.min_bet,
        ante=args.ante,
        max_raises=args.max_raises,
    )

    for game_id in range(1, args.games + 1):
        result = engine.play_game(game_id, rules)
        if logger:
            logger.log(result)
        stats.update(result)

    if logger:
        logger.close()

    flush_llm_caches(seats)
    llm_metrics = collect_llm_metrics(seats)
    summary = stats.summary(seats, llm_metrics)

    print("=" * 60)
    print("🏁 游戏结束统计:")
    print(
        f"总局数: {summary['total_games']} | 有效局数: {summary['games_played']} | 平局: {summary['draws']}"
    )
    for player in summary["players"]:
        win_rate = player["win_rate"]
        fold_rate = player["fold_rate"]
        delta = player["bankroll_change"]
        delta_str = f"{delta:+d}" if delta else "0"
        bet_mode = player.get("bet_mode", "n/a")
        print(
            f"- {player['name']}: 资金 {player['bankroll']} ({delta_str}) | 胜场 {player['wins']} ({win_rate:.1%}) | "
            f"弃牌 {player['folds']} ({fold_rate:.1%}) | 平均换牌 {player['avg_discards']:.2f}"
        )
        if bet_mode != "n/a":
            print(f"    · 下注策略: {bet_mode}")
        metrics = player.get("llm_metrics")
        if metrics:
            print(
                f"    · LLM: 调用 {metrics.get('api_calls', 0)} | 缓存命中率 {metrics.get('cache_hit_rate', 0.0):.1%} | 回退 {metrics.get('fallbacks', 0)}"
            )
    print("=" * 60 + "\n")

    print(json.dumps(summary, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
def parse_bet_modes(
    string: Optional[str], count: int, default: str
) -> List[str]:
    if not string:
        return [default for _ in range(count)]
    parts = [part.strip().lower() for part in string.split(",")]
    if len(parts) != count:
        raise ValueError("Number of bet modes must match number of agents")
    modes: List[str] = []
    for part in parts:
        mode = part or default
        if mode not in {"heuristic", "llm"}:
            raise ValueError("Bet modes must be 'heuristic' or 'llm'")
        modes.append(mode)
    return modes
