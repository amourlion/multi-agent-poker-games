"""LLM-powered agent for Five-card draw discard decisions."""

from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Optional

from deck import Card, hand_to_str
from game_types import (
    BetDecision,
    BettingAction,
    BettingContext,
    DecisionContext,
    DecisionRules,
    DiscardDecision,
)
from hand_eval import evaluate_hand

try:
    from openai import AzureOpenAI  # type: ignore
except ImportError:  # pragma: no cover - optional dependency
    AzureOpenAI = None  # type: ignore


DEFAULT_API_VERSION = "2025-01-01-preview"
DEFAULT_DEPLOYMENT_NAME = "gpt-4o-new"
DEFAULT_MODEL_ID = "azure_openai:gpt-4o"


def _rank_value(rank: str) -> int:
    order = "23456789TJQKA"
    return order.index(rank) + 2


def _conservative_fallback(hand: List[Card], rules: DecisionRules) -> DiscardDecision:
    max_allowed = min(rules.max_discards, 3)
    if max_allowed <= 0:
        return DiscardDecision([])
    values = [_rank_value(card.rank) for card in hand]
    counts: Dict[int, int] = {}
    for value in values:
        counts[value] = counts.get(value, 0) + 1
    keep_indices = {
        index for index, value in enumerate(values) if counts[value] >= 2
    }
    discard_candidates = [
        (values[index], index) for index in range(len(hand)) if index not in keep_indices
    ]
    discard_candidates.sort()
    chosen = [index for _, index in discard_candidates[:max_allowed]]
    return DiscardDecision(sorted(chosen), rationale="Fallback: keep made pairs")


class DecisionCache:
    """Simple disk-backed cache for LLM discard decisions."""

    def __init__(self, path: Optional[str] = None) -> None:
        self._path = path
        self._entries: Dict[str, Dict[str, Any]] = {}
        self._dirty = False
        if path and os.path.exists(path):
            with open(path, "r", encoding="utf-8") as handle:
                data = json.load(handle)
            if isinstance(data, dict):
                self._entries.update(data)

    def get(self, key: str) -> Optional[DiscardDecision]:
        value = self._entries.get(key)
        if value is None:
            return None
        return DiscardDecision(list(value["discard_indices"]), value.get("rationale"))

    def set(self, key: str, decision: DiscardDecision) -> None:
        self._entries[key] = {
            "discard_indices": list(decision.discard_indices),
            "rationale": decision.rationale,
        }
        self._dirty = True

    def sync(self) -> None:
        if not self._path or not self._dirty:
            return
        directory = os.path.dirname(self._path)
        if directory:
            os.makedirs(directory, exist_ok=True)
        with open(self._path, "w", encoding="utf-8") as handle:
            json.dump(self._entries, handle, ensure_ascii=False, indent=2)
        self._dirty = False


def _canonicalize_hand(hand: Iterable[Card]) -> str:
    suit_order: Dict[str, str] = {}
    next_symbol = ord("a")
    parts = []
    for card in sorted(hand, key=lambda c: (_rank_value(c.rank), c.suit), reverse=True):
        mapped = suit_order.get(card.suit)
        if mapped is None:
            mapped = chr(next_symbol)
            suit_order[card.suit] = mapped
            next_symbol += 1
        parts.append(f"{card.rank}{mapped}")
    return "-".join(parts)


JSON_SCHEMA = {
    "type": "json_schema",
    "json_schema": {
        "name": "DiscardDecision",
        "schema": {
            "type": "object",
            "properties": {
                "discard_indices": {
                    "type": "array",
                    "items": {
                        "type": "integer",
                        "minimum": 0,
                        "maximum": 4,
                    },
                    "minItems": 0,
                    "maxItems": 5,
                },
                "rationale": {"type": "string"},
            },
            "required": ["discard_indices"],
            "additionalProperties": False,
        },
    },
}


SYSTEM_PROMPT = (
    "You are a poker assistant playing Five-card draw.\n"
    "Rules: one draw round; you may discard 0-5 cards once; unknown cards are uniformly random.\n"
    "Goal: maximize final 5-card hand strength.\n"
    "Output strictly in the required JSON schema. No extra text."
)


BET_JSON_SCHEMA = {
    "type": "json_schema",
    "json_schema": {
        "name": "BetDecision",
        "schema": {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": [action.value for action in BettingAction],
                },
                "amount": {
                    "type": "integer",
                    "minimum": 0,
                },
                "rationale": {
                    "type": "string",
                },
            },
            "required": ["action"],
            "additionalProperties": False,
        },
    },
}


BET_SYSTEM_PROMPT = (
    "You are a poker betting assistant for Five-card draw.\n"
    "Only one betting round occurs before the draw.\n"
    "Choose the best action among the allowed options.\n"
    "If the evaluated hand is already strong (pairs or better), favour aggressive betting/raising even if it means higher risk.\n"
    "Respond strictly with the required JSON schema."
)


@dataclass
class LLMAgentMetrics:
    cache_hits: int = 0
    cache_misses: int = 0
    api_calls: int = 0
    fallbacks: int = 0
    invalid_responses: int = 0

    def as_dict(self) -> Dict[str, float]:
        total_cache = self.cache_hits + self.cache_misses
        hit_rate = (self.cache_hits / total_cache) if total_cache else 0.0
        return {
            "cache_hits": self.cache_hits,
            "cache_misses": self.cache_misses,
            "cache_hit_rate": hit_rate,
            "api_calls": self.api_calls,
            "fallbacks": self.fallbacks,
            "invalid_responses": self.invalid_responses,
        }


class LLMAgent:
    """Agent that delegates discard selection to an OpenAI model."""

    def __init__(
        self,
        *,
        model: str = os.environ.get("AZURE_OPENAI_DEPLOYMENT_NAME", DEFAULT_DEPLOYMENT_NAME),
        temperature: float = 0.0,
        max_retries: int = 3,
        timeout: float = 5.0,
        client: Optional[Any] = None,
        cache_path: Optional[str] = None,
        bet_mode: str = "heuristic",
    ) -> None:
        self.model = model
        self.temperature = temperature
        self.max_retries = max_retries
        self.timeout = timeout
        self._client = client
        self._client_checked = client is not None
        self._cache = DecisionCache(cache_path)
        self._metrics = LLMAgentMetrics()
        self._quota_error_shown = False  # 标记是否已显示配额错误提示
        self.bet_mode = bet_mode if bet_mode in {"heuristic", "llm"} else "heuristic"

    @staticmethod
    def create_default_client() -> Any:
        if AzureOpenAI is None:
            print(
                "⚠️ 未安装 openai 库（或版本过旧），"
                "请运行 `uv pip install \"openai>=1.14\"` 后重试"
            )
            return None

        api_key = os.environ.get("AZURE_OPENAI_API_KEY")
        endpoint = os.environ.get("AZURE_OPENAI_ENDPOINT")
        api_version = os.environ.get("OPENAI_API_VERSION", DEFAULT_API_VERSION)
        if not api_key or not endpoint:
            print(
                "⚠️ 缺少 AZURE_OPENAI_API_KEY 或 AZURE_OPENAI_ENDPOINT 环境变量，"
                "LLM 代理将回退到保守策略"
            )
            return None

        # 检查代理设置
        http_proxy = os.environ.get("HTTP_PROXY") or os.environ.get("http_proxy")
        https_proxy = os.environ.get("HTTPS_PROXY") or os.environ.get("https_proxy")

        if http_proxy or https_proxy:
            print(f"🌐 检测到代理设置: HTTP={http_proxy}, HTTPS={https_proxy}")

        return AzureOpenAI(
            api_key=api_key,
            azure_endpoint=endpoint,
            api_version=api_version,
        )

    def metrics(self) -> Dict[str, float]:
        return self._metrics.as_dict()

    def flush_cache(self) -> None:
        self._cache.sync()

    def decide_discard(
        self, hand: List[Card], rules: DecisionRules, context: DecisionContext
    ) -> DiscardDecision:
        key = self._cache_key(hand, rules)
        cached = self._cache.get(key)
        if cached is not None:
            self._metrics.cache_hits += 1
            return cached

        self._metrics.cache_misses += 1
        decision = None
        client = self._ensure_client()
        if client is not None:
            decision = self._call_llm_with_retries(client, hand, rules)
        if decision is None or not self._validate_decision(decision, len(hand), rules):
            self._metrics.fallbacks += 1
            decision = _conservative_fallback(hand, rules)
        self._cache.set(key, decision)
        return decision

    def _cache_key(self, hand: Iterable[Card], rules: DecisionRules) -> str:
        canonical = _canonicalize_hand(hand)
        return f"{self.model}|{rules.max_discards}|{canonical}"

    def _ensure_client(self) -> Optional[Any]:
        if self._client_checked:
            return self._client
        self._client_checked = True
        client = self.create_default_client()
        self._client = client
        return client

    def _call_llm_with_retries(
        self, client: Any, hand: List[Card], rules: DecisionRules
    ) -> Optional[DiscardDecision]:
        payload = {
            "hand": hand_to_str(hand),
            "rules": {"max_discards": rules.max_discards},
            "task": "Return indices of cards to discard (0-4).",
        }
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
        ]
        for attempt in range(1, self.max_retries + 1):
            try:
                self._metrics.api_calls += 1
                response = client.chat.completions.create(  # type: ignore[attr-defined]
                    model=self.model,
                    temperature=self.temperature,
                    response_format=JSON_SCHEMA,
                    messages=messages,
                    timeout=self.timeout,
                )
                
                # 简化响应处理逻辑
                content = None
                if hasattr(response, 'choices') and response.choices:
                    message = response.choices[0].message
                    if hasattr(message, 'content') and message.content:
                        content = message.content
                
                if not content:
                    raise ValueError("Empty LLM response")
                    
                parsed = json.loads(content)
                decision = DiscardDecision(
                    discard_indices=list(parsed.get("discard_indices", [])),
                    rationale=parsed.get("rationale"),
                )
                return decision
            except Exception as e:
                # 提供用户友好的错误提示
                if "insufficient_quota" in str(e):
                    if not self._quota_error_shown:  # 只显示一次详细提示
                        print("💳 OpenAI API配额不足!")
                        print("   原因：OpenAI现在要求添加付费方式才能使用API")
                        print("   解决方案：")
                        print("   1. 访问 https://platform.openai.com/account/billing/overview")
                        print("   2. 添加信用卡或借记卡作为付费方式")
                        print("   3. 设置使用限额（可设置低金额如$5）")
                        print("   4. 程序将自动回退到保守策略继续运行")
                        self._quota_error_shown = True
                elif "model_not_found" in str(e):
                    print(f"🤖 模型 {self.model} 不可用，请检查模型名称或权限")
                elif "Connection error" in str(e):
                    print("🌐 网络连接错误，请检查代理设置或网络连接")
                
                self._metrics.invalid_responses += 1
                if attempt >= self.max_retries:
                    break
                backoff = 0.5 * (2 ** (attempt - 1))
                time.sleep(backoff)
        return None

    def _validate_decision(
        self, decision: DiscardDecision, hand_size: int, rules: DecisionRules
    ) -> bool:
        indices = decision.discard_indices
        if any((not isinstance(idx, int)) for idx in indices):
            return False
        if any(idx < 0 or idx >= hand_size for idx in indices):
            return False
        if len(set(indices)) != len(indices):
            return False
        if len(indices) > rules.max_discards:
            return False
        return True

    def decide_bet(
        self, hand: List[Card], context: BettingContext
    ) -> BetDecision:
        if self.bet_mode == "llm":
            client = self._ensure_client()
            if client is not None:
                decision = self._call_bet_llm_with_retries(client, hand, context)
                if decision and self._validate_bet(decision, context):
                    return decision
        evaluation = evaluate_hand(hand)
        available = set(context.available_actions)
        strength = evaluation.rank_id
        rng = context.rng

        if BettingAction.CHECK in available and context.to_call == 0:
            can_bet = (
                BettingAction.BET in available and context.stack >= context.min_bet
            )
            should_bet = False
            if can_bet:
                if strength >= 4:  # straight or better
                    should_bet = True
                elif strength >= 2:  # two pair or better
                    should_bet = rng.random() < 0.9
                elif strength == 1:  # one pair
                    should_bet = rng.random() < 0.75
                else:  # high card
                    should_bet = rng.random() < 0.5
            if should_bet and can_bet:
                if strength >= 4:
                    divisor = 3
                elif strength >= 2:
                    divisor = 4
                elif strength == 1:
                    divisor = 6
                else:
                    divisor = 8
                baseline = max(context.stack // divisor, context.min_bet)
                amount = max(context.min_bet, baseline)
                amount = min(amount, context.stack)
                rationale = f"LLM heuristic: bet with {evaluation.rank_name}"
                return BetDecision(BettingAction.BET, amount, rationale)
            return BetDecision(BettingAction.CHECK, rationale="LLM heuristic: check")

        call_amount = min(context.to_call, context.stack)

        if BettingAction.CALL in available and call_amount > 0:
            comfortable_call = max(context.min_bet, context.stack // 4)
            speculative_call = max(context.min_bet, context.stack // 6)
            if strength >= 4 or (
                strength >= 2 and call_amount <= comfortable_call
            ) or (
                strength == 1 and call_amount <= comfortable_call
            ) or (
                strength == 0 and call_amount <= speculative_call and rng.random() < 0.6
            ) or (
                call_amount <= context.min_bet and rng.random() < 0.5
            ):
                if (
                    BettingAction.RAISE in available
                    and context.stack > call_amount + context.min_raise
                ):
                    raise_chance = 0.0
                    if strength >= 6:
                        raise_chance = 0.9
                    elif strength >= 5:
                        raise_chance = 0.8
                    elif strength == 4:
                        raise_chance = 0.65
                    elif strength == 3:
                        raise_chance = 0.45
                    elif strength == 2:
                        raise_chance = 0.3
                    elif strength == 1:
                        raise_chance = 0.2
                    elif strength == 0:
                        raise_chance = 0.1
                    if rng.random() < raise_chance:
                        desired = call_amount + max(context.min_raise, context.min_bet)
                        raise_target = min(desired, context.stack)
                        rationale = f"LLM heuristic: raise with {evaluation.rank_name}"
                        return BetDecision(BettingAction.RAISE, raise_target, rationale)
                rationale = f"LLM heuristic: call with {evaluation.rank_name}"
                return BetDecision(BettingAction.CALL, call_amount, rationale)
            if (
                BettingAction.RAISE in available
                and context.stack > call_amount + context.min_raise
                and rng.random() < 0.25
            ):
                desired = call_amount + max(context.min_raise, context.min_bet)
                raise_target = min(desired, context.stack)
                rationale = f"LLM heuristic: semi-bluff raise with {evaluation.rank_name}"
                return BetDecision(BettingAction.RAISE, raise_target, rationale)

        if BettingAction.FOLD in available:
            return BetDecision(BettingAction.FOLD, rationale="LLM heuristic: fold weak hand")

        if BettingAction.CALL in available:
            return BetDecision(
                BettingAction.CALL,
                call_amount,
                rationale="LLM fallback: forced call",
            )

        return BetDecision(BettingAction.CHECK, rationale="LLM fallback: forced check")

    def _validate_bet(self, decision: BetDecision, context: BettingContext) -> bool:
        if decision.action not in context.available_actions:
            return False
        if decision.amount < 0:
            return False
        if decision.action == BettingAction.CALL and decision.amount > context.stack:
            return False
        return True

    def _call_bet_llm_with_retries(
        self, client: Any, hand: List[Card], context: BettingContext
    ) -> Optional[BetDecision]:
        payload = {
            "hand": hand_to_str(hand),
            "hand_rank": evaluate_hand(hand).rank_name,
            "pot": context.pot,
            "to_call": context.to_call,
            "current_bet": context.current_bet,
            "stack": context.stack,
            "min_bet": context.min_bet,
            "min_raise": context.min_raise,
            "available_actions": [action.value for action in context.available_actions],
        }
        messages = [
            {"role": "system", "content": BET_SYSTEM_PROMPT},
            {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
        ]
        for attempt in range(1, self.max_retries + 1):
            try:
                self._metrics.api_calls += 1
                response = client.chat.completions.create(  # type: ignore[attr-defined]
                    model=self.model,
                    temperature=self.temperature,
                    response_format=BET_JSON_SCHEMA,
                    messages=messages,
                    timeout=self.timeout,
                )
                content = None
                if hasattr(response, "choices") and response.choices:
                    message = response.choices[0].message
                    if hasattr(message, "content") and message.content:
                        content = message.content
                if not content:
                    raise ValueError("Empty LLM response")

                parsed = json.loads(content)
                action_raw = parsed.get("action")
                if not isinstance(action_raw, str):
                    raise ValueError("Invalid action returned")
                action_value = action_raw.lower()
                try:
                    action = BettingAction(action_value)
                except ValueError as exc:
                    raise ValueError(f"Unsupported action: {action_value}") from exc
                amount = parsed.get("amount", 0)
                if not isinstance(amount, int):
                    raise ValueError("Amount must be integer")
                rationale = parsed.get("rationale")
                return BetDecision(action=action, amount=amount, rationale=rationale)
            except Exception as exc:  # noqa: BLE001
                self._metrics.invalid_responses += 1
                if self.bet_mode == "llm":
                    if "insufficient_quota" in str(exc) and not self._quota_error_shown:
                        print("💳 OpenAI API配额不足 (betting call)!")
                        self._quota_error_shown = True
                if attempt >= self.max_retries:
                    break
                backoff = 0.5 * (2 ** (attempt - 1))
                time.sleep(backoff)
        self._metrics.fallbacks += 1
        return None


__all__ = [
    "LLMAgent",
    "DEFAULT_API_VERSION",
    "DEFAULT_DEPLOYMENT_NAME",
    "DEFAULT_MODEL_ID",
]
