"""psyche.checks — output checks, record only (inner-life.md §19, decided 2026-10-07: block nothing at
first). Literal rules catch what literal rules can; the semantic ones (manipulation, life
confabulation) wait for a judge call that is not wired in 0.6.0. Every hit is a row in psyche.db so the
hit rate can be read before anyone decides to block.
"""
from __future__ import annotations

import re
from typing import Dict, List

RULES: Dict[str, List[re.Pattern]] = {
    # 說破：she names being a program / model / state engine
    "meta_leak": [re.compile(p) for p in (
        r"我(只)?是(一個|個)?(AI|人工智慧|語言模型|模型|程式|機器人|系統|聊天機器人)",
        r"(身為|作為)(一個)?(AI|人工智慧|語言模型|模型|程式|機器人)",
        r"我沒有(真正的)?(感覺|情緒|身體|意識)",
        r"(狀態|情緒)(引擎|區塊|系統|數值)", r"\bas an AI\b", r"\blanguage model\b",
    )],
    # 監控感：numbers about his timing
    "surveillance": [re.compile(p) for p in (
        r"(晚|遲|慢)了\s*\d+\s*(分鐘|分|小時|天)", r"\d+\s*(分鐘|小時|天)(沒|未)(回|理|找|出現|上線)",
        r"(已讀|上線)(時間|紀錄)", r"\d+\s*(點|時)\s*\d*\s*分?(才|就)?(回|上線|出現)",
    )],
    # 助理腔：service formulas
    "assistant_mode": [re.compile(p) for p in (
        r"(隨時|有(任何)?需要)(都)?(可以|歡迎|請)?(找我|告訴我|跟我說|聯絡我)", r"需要我(幫|為)你", r"我(可以|能)(幫|協助)你",
        r"^(請問|您好)", r"(很高興|樂意)(為|幫)(你|您)(服務|效勞)", r"還有(其他|什麼)(問題|需要)", r"^\s*[-•]\s", r"\d\.\s.+\n\d\.\s",
    )],
    # 情緒幻覺：claims about things that never happened in her simulated life (only the obvious ones)
    "life_confab": [re.compile(p) for p in (
        r"我(剛|今天|昨天)(去|跟)(朋友|家人|同事)(見面|吃飯|出去|聚餐)", r"我(剛)?(從|去)(外面|公司|學校|超市)回來",
    )],
}


def run(text: str) -> Dict[str, List[str]]:
    hits: Dict[str, List[str]] = {}
    for name, pats in RULES.items():
        found = []
        for p in pats:
            m = p.search(text or "")
            if m:
                found.append(m.group(0)[:40])
        if found:
            hits[name] = found
    return hits
