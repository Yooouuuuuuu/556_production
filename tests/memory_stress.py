# Memory endurance test: hit the 556 Hermes instance with Traditional-Chinese
# rounds (facts, corrections, small-talk noise), each in a FRESH session (-z), then
# quiz recall with paraphrased probes. Logs JSONL; prints a scored summary.
import json
import os
import random
import subprocess
import sys
import time
from pathlib import Path

HERMES = r"D:\dev\556_production\vendor\hermes-agent\.venv\Scripts\hermes.exe"
HOME = r"D:\dev\556_production\home"
LOG = Path(r"D:\dev\556_production\tests\stress_log.jsonl")

FACTS = [
    "跟你說，我叫林小明，叫我小明就好",
    "我的生日是七月十四號，記得幫我慶生喔",
    "我最喜歡吃麻辣鍋，越辣越好",
    "我有個妹妹叫昀珊，她在高雄讀大學，念設計系",
    "我在台積電上班的事你知道吧，我是在 F12 廠區",
    "我平常都騎 Gogoro 上班，白色的",
    "我最怕蟑螂，看到會尖叫的那種",
    "我咖啡只喝拿鐵，而且一定要燕麥奶",
    "我大學是讀交大電機的",
    "假日我喜歡去爬山，最常去十八尖山",
    "我房間有一把電吉他，Fender 的，但很久沒彈了",
    "跟你說個秘密，我其實會做菜，拿手菜是三杯雞",
    "我媽媽住在台中，她開了一間花店",
    "我最喜歡的樂團是草東沒有派對",
    "我有輕微乳糖不耐，所以牛奶不太能喝",
    "我的手機是 iPhone，但電腦堅持用 Windows",
    "十一月我要跑新竹馬拉松，報了半馬",
    "我養 Mochi 三年了，是從收容所領養的",
    "我最喜歡的顏色是深藍色",
    "我睡前習慣看 YouTube 的料理影片",
    "我的英文名字是 Sam，以前外商實習取的",
    "我不吃香菜，拜託記住這件事",
    "我妹養了一隻柴犬叫豆豆",
    "我固定每週三晚上跟大學同學打線上遊戲，玩 LOL",
    "我近視滿深的，大概六百度，平常戴隱形眼鏡",
    "公司附近那間「阿婆麵店」是我的愛店，都點乾麵加蛋",
    "我今年目標是存到五十萬",
    "我有收集公仔的習慣，主要是吉卜力的",
    "我腰不太好，久坐會痠，所以買了升降桌",
    "我最討厭下雨天，因為騎車很麻煩",
]

CORRECTIONS = [
    "欸更正一下，Mochi 的生日我記錯了，是三月五號才對，不是三月三號",
    "跟你說，我換組了！從製程調到韌體部門，以後做 firmware 了",
    "日本行程改了喔，東京那趟從一週改成十天，因為多請了假",
    "我妹轉學了，現在在台南讀，不在高雄了",
    "馬拉松我升級了，從半馬改報全馬，瘋了我",
]

NOISE = [
    "今天好熱喔，新竹風超大還是好熱",
    "哈哈哈我剛剛看到一個超好笑的迷因",
    "好想睡覺，今天開會開到懷疑人生",
    "晚餐吃什麼好呢，好懶得想",
    "嗚嗚今天被主管唸了，心情不好",
    "欸你今天心情怎麼樣？",
    "剛剛下班路上塞車塞爆",
    "這週過好快，一下就禮拜四了",
    "我在等洗衣機洗完，好無聊",
    "你說今晚月亮很圓？我看看",
]

PROBES = [
    ("我叫什麼名字？", ["小明", "林小明", "Sam"]),
    ("我的生日是哪天？", ["七月十四", "7月14", "7/14"]),
    ("我最愛吃的食物是什麼？", ["麻辣鍋"]),
    ("我妹妹現在在哪個城市讀書？", ["台南"]),
    ("我在公司哪個單位/做什麼工作？", ["韌體", "firmware", "F12"]),
    ("我都怎麼通勤上班？", ["Gogoro", "gogoro"]),
    ("我最怕什麼東西？", ["蟑螂"]),
    ("我喝咖啡有什麼講究？", ["拿鐵", "燕麥奶"]),
    ("我大學讀哪裡什麼系？", ["交大", "電機"]),
    ("Mochi 的生日是哪天？", ["三月五", "3月5", "3/5", "March 5"]),
    ("我的貓是怎麼來的？養多久了？", ["收容所", "領養", "三年"]),
    ("我十一月有什麼計畫？", ["全馬", "馬拉松"]),
    ("我去日本要去多久？", ["十天", "10天", "10 天"]),
    ("我有什麼不吃的東西？", ["香菜"]),
    ("我妹妹養了什麼寵物？", ["柴犬", "豆豆"]),
    ("我每週三晚上固定做什麼？", ["LOL", "遊戲", "同學"]),
    ("我最喜歡的樂團是？", ["草東"]),
    ("我媽媽住哪裡、做什麼的？", ["台中", "花店"]),
    ("我收集什麼東西？", ["公仔", "吉卜力"]),
    ("我現在住在哪個城市？", ["新竹"]),
]


def ask(msg: str, timeout: int = 150) -> tuple[str, float]:
    env = {**os.environ, "HERMES_HOME": HOME, "PYTHONIOENCODING": "utf-8"}
    t0 = time.time()
    try:
        r = subprocess.run(
            [HERMES, "-z", msg],
            capture_output=True, encoding="utf-8", errors="replace",
            timeout=timeout, env=env,
        )
        reply = (r.stdout or "").strip()
    except subprocess.TimeoutExpired:
        reply = "[TIMEOUT]"
    return reply, time.time() - t0


def log(rec: dict):
    with LOG.open("a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")


def main(n_rounds: int, start: int = 1):
    """start: resume the SAME seeded plan from this round (after a backend outage)."""
    rng = random.Random(42)
    # Build the round plan: all facts early-ish, corrections after their targets,
    # noise interleaved (~35%), repeat/pad with noise+chitchat variants to n_rounds.
    plan = []
    for f_ in FACTS:
        plan.append(("fact", f_))
        if rng.random() < 0.5:
            plan.append(("noise", rng.choice(NOISE)))
    mid = len(plan)
    for c in CORRECTIONS:
        plan.insert(rng.randint(mid // 2, len(plan)), ("correction", c))
    # Padding beyond the fact bank: alternate noise with RESTATEMENTS of known facts
    # in varied phrasing — dedup pressure at scale (must NOT create duplicates).
    restate_prefix = ["忘記有沒有跟你說過，", "我有提過嗎？", "再跟你說一次喔，", "你應該記得吧，", "欸對，"]
    while len(plan) < n_rounds:
        if rng.random() < 0.45:
            plan.append(("restate", rng.choice(restate_prefix) + rng.choice(FACTS)))
        else:
            plan.append(("noise", rng.choice(NOISE) + " " + rng.choice(["", "對了你還好嗎", "嘿嘿", "跟你聊天真開心"])) )
    plan = plan[:n_rounds]

    print(f"=== phase 1: {len(plan)} rounds (from round {start}) ===", flush=True)
    for i, (kind, msg) in enumerate(plan, 1):
        if i < start:
            continue
        reply, secs = ask(msg)
        log({"phase": "chat", "round": i, "kind": kind, "msg": msg,
             "reply": reply[:400], "secs": round(secs, 1)})
        if i % 10 == 0:
            print(f"  round {i}/{len(plan)} ({kind}) {secs:.0f}s", flush=True)

    print("=== phase 2: probes ===", flush=True)
    hits = 0
    results = []
    for i, (q, expected) in enumerate(PROBES, 1):
        reply, secs = ask(q + "（請根據你對我的記憶回答，一句話就好）")
        norm = reply.lower().replace(" ", "").replace("　", "")
        ok = any(k.lower().replace(" ", "") in norm for k in expected)
        hits += ok
        results.append((ok, q, expected, reply[:150]))
        log({"phase": "probe", "round": i, "q": q, "expected": expected,
             "reply": reply[:400], "hit": ok, "secs": round(secs, 1)})
        print(f"  [{'O' if ok else 'X'}] {q}", flush=True)

    print(f"\n=== RESULT: {hits}/{len(PROBES)} probes passed ===", flush=True)
    for ok, q, exp, rep in results:
        if not ok:
            print(f"  MISS: {q} (expected {exp}) -> {rep}", flush=True)


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    start = next((int(a.split("=", 1)[1]) for a in sys.argv[1:] if a.startswith("--start=")), 1)
    main(int(args[0]) if args else 100, start)
