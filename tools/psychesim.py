"""psychesim — the offline engine simulator (inner-life.md §20): run her inner life on a fake clock with
no LLM and print what a day, a week or a thousand seeds look like.

    python tools/psychesim.py week                 # 7 days alone after one turn: phases, sleep, urges
    python tools/psychesim.py day --chat 20,22     # a day with a conversation from 20:00 to 22:00
    python tools/psychesim.py seeds 1000           # stability sweep: 1000 characters × 24 h, bounds and NaNs
    python tools/psychesim.py replay               # replay == live check on a 2-day run

Uses the plugin's defaults (plugins/psyche/config.py) unless --config <psyche.json> is given.
"""
from __future__ import annotations

import argparse
import copy
import json
import math
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "plugins"))
from psyche import config  # noqa: E402
from psyche.engine import Engine  # noqa: E402

TZ = timezone(timedelta(hours=8))


class Clock:
    def __init__(self, t):
        self.t = t

    def __call__(self):
        return self.t


def engine(tmp, name, clock, cfg, char="test"):
    e = Engine(Path(tmp), char, cfg, db_path=Path(tmp) / f"{name}.db", now_fn=clock, llm=None)
    e.owner = True
    e.load()
    e.live = True
    return e


def run(e, clock, hours, hook=None):
    for _ in range(int(hours * 60)):
        clock.t += 60
        e.step_to(clock.t)
        if hook:
            hook(e, clock)


def fmt(e):
    s = e.status()
    return (f"{e.local(s['t']).strftime('%a %H:%M')} {s['activity']:6s} E={s['energy']:.2f} S={s['sleep']['S']:.2f} "
            f"P={s['affect']['pos']:.2f} N={s['affect']['neg']:.2f} mood={s['octant_zh']}({s['strength']:.2f}) "
            f"need_p={s['needs']['affiliation_person']:.2f} nov={s['needs']['novelty']:.2f} phase={s['contact']['phase']} "
            f"inst={[(i['type'], round(i['intensity'], 2)) for i in s['instances'][:3]]}")


def cmd_week(cfg, t0):
    with tempfile.TemporaryDirectory() as tmp:
        clock = Clock(t0)
        e = engine(tmp, "week", clock, cfg)
        e.on_turn("我先去忙了", "好。", turn_id="t0", platform="api_server", session_id="s")

        def hook(eng, ck):
            if eng.contact.get("pending") and not getattr(eng, "_sim_marked", None) == eng.contact["pending"]["tick"]:
                eng._sim_marked = eng.contact["pending"]["tick"]
                print(f"   {eng.local(ck.t).strftime('%a %H:%M')} URGE {eng.contact['pending']['kind']} {eng.contact['pending']['what']}")
                eng.on_event_reply("【事件】", "在嗎？", platform="api_server")
        for day in range(7):
            run(e, clock, 24, hook)
            print(f"day {day + 1}: {fmt(e)}")
        kinds = e.conn.execute("select kind, count(*) from events group by kind order by 2 desc").fetchall()
        print("events:", kinds)
        print("state block:\n" + "\n".join("   " + ln for ln in e.state_block().splitlines()))
        e.conn.close()


def cmd_day(cfg, t0, chat):
    with tempfile.TemporaryDirectory() as tmp:
        clock = Clock(t0)
        e = engine(tmp, "day", clock, cfg)
        a, b = (float(x) for x in chat.split(",")) if chat else (None, None)
        for h in range(24):
            for m in range(0, 60, 5):
                clock.t += 300
                hour = e.local(clock.t).hour + e.local(clock.t).minute / 60
                if a is not None and a <= hour < b:
                    e.on_turn("聊聊", "嗯。", turn_id=f"t{clock.t}", platform="api_server", session_id="s")
                e.step_to(clock.t)
            print(fmt(e))
        e.conn.close()


def cmd_seeds(cfg, t0, n):
    bad = 0
    lo = {"pos": 9, "neg": 9, "mood": 9}
    hi = {"pos": -9, "neg": -9, "mood": -9}
    with tempfile.TemporaryDirectory() as tmp:
        for i in range(n):
            clock = Clock(t0)
            e = engine(tmp, f"s{i}", clock, cfg, char=f"c{i}")
            run(e, clock, 24)
            s = e.status()
            vals = [s["affect"]["pos"], s["affect"]["neg"], *s["mood"], s["energy"], *s["needs"].values()]
            if any(math.isnan(v) or math.isinf(v) for v in vals):
                bad += 1
            lo["pos"], hi["pos"] = min(lo["pos"], s["affect"]["pos"]), max(hi["pos"], s["affect"]["pos"])
            lo["neg"], hi["neg"] = min(lo["neg"], s["affect"]["neg"]), max(hi["neg"], s["affect"]["neg"])
            lo["mood"], hi["mood"] = min(lo["mood"], s["mood"][0]), max(hi["mood"], s["mood"][0])
            e.conn.close()
            (Path(tmp) / f"s{i}.db").unlink(missing_ok=True)
    print(json.dumps({"seeds": n, "nan_or_inf": bad, "pos": [round(lo["pos"], 3), round(hi["pos"], 3)],
                      "neg": [round(lo["neg"], 3), round(hi["neg"], 3)], "mood_p": [round(lo["mood"], 3), round(hi["mood"], 3)]}))


def cmd_replay(cfg, t0):
    with tempfile.TemporaryDirectory() as tmp:
        clock = Clock(t0)
        e = engine(tmp, "r", clock, cfg)
        e.on_turn("晚安", "晚安。", turn_id="a", platform="api_server", session_id="s")
        run(e, clock, 30)
        e.on_turn("早安", "早。", turn_id="b", platform="api_server", session_id="s")
        run(e, clock, 18)
        live = e.status()
        e2 = Engine(Path(tmp), "test", cfg, db_path=Path(tmp) / "r.db", now_fn=clock, llm=None)
        e2.owner = True
        e2.load()
        rep = e2.status()
        same = all(abs(live["affect"][k] - rep["affect"][k]) < 1e-9 for k in live["affect"]) and live["activity"] == rep["activity"] \
            and [i["id"] for i in live["instances"]] == [i["id"] for i in rep["instances"]]
        print("replay == live:", same)
        e.conn.close()
        e2.conn.close()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["week", "day", "seeds", "replay"])
    ap.add_argument("n", nargs="?", type=int, default=100)
    ap.add_argument("--chat", default="")
    ap.add_argument("--config", default="")
    ap.add_argument("--start", default="2026-10-12T20:00")
    args = ap.parse_args()
    cfg = copy.deepcopy(config.DEFAULTS)
    if args.config:
        cfg = config._merge(cfg, json.loads(Path(args.config).read_text(encoding="utf-8-sig")))
    t0 = datetime.fromisoformat(args.start).replace(tzinfo=TZ).timestamp()
    t0 -= t0 % 60
    if args.cmd == "week":
        cmd_week(cfg, t0)
    elif args.cmd == "day":
        cmd_day(cfg, t0, args.chat)
    elif args.cmd == "seeds":
        cmd_seeds(cfg, t0, args.n)
    else:
        cmd_replay(cfg, t0)
    return 0


if __name__ == "__main__":
    sys.exit(main())
