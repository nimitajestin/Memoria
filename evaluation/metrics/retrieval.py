"""Retrieval ranking metrics. Gold labels are chunk or memory ids."""

from __future__ import annotations

import math


def recall_at_k(gold: list[str], ranked: list[str], k: int) -> float:
    if not gold:
        return 0.0
    hits = set(ranked[:k]) & set(gold)
    return len(hits) / len(set(gold))


def precision_at_k(gold: list[str], ranked: list[str], k: int) -> float:
    top = ranked[:k]
    if not top:
        return 0.0
    return len(set(top) & set(gold)) / len(top)


def mrr(gold: list[str], ranked: list[str]) -> float:
    wanted = set(gold)
    for index, item in enumerate(ranked, start=1):
        if item in wanted:
            return 1.0 / index
    return 0.0


def ndcg_at_k(gold: list[str], ranked: list[str], k: int) -> float:
    wanted = set(gold)
    dcg = 0.0
    for index, item in enumerate(ranked[:k], start=1):
        if item in wanted:
            dcg += 1.0 / math.log2(index + 1)
    ideal = min(k, len(wanted))
    idcg = sum(1.0 / math.log2(index + 1) for index in range(1, ideal + 1))
    if idcg == 0.0:
        return 0.0
    return dcg / idcg


def macro_mean(values: list[float]) -> float:
    if not values:
        return 0.0
    return sum(values) / len(values)
