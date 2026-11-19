"""
把 GitHub 贡献记录画成一张会动的 K 线图（$TICKER 走势），用于 GitHub 个人主页 README。

"价格" = 最近 7 天的贡献数（滚动求和）
每根 K 线 = 一周：开盘 = 周一的价格，收盘 = 周日的价格，最高/最低 = 这一周里的最高/最低
成交量 = 这一周的贡献总数
均线 = 最近 MA_WINDOW（7）根 K 线收盘价的平均

用法：
  GITHUB_TOKEN=... python kline.py --user yewenyiywy --out dist
  python kline.py --demo --out dist            # 用模拟数据生成预览
输出 dist/kline.svg（浅色）和 dist/kline-dark.svg（深色）
"""
import argparse
import datetime as dt
import json
import os
import random
import urllib.request
from html import escape

TICKER = "WENYI"
MA_WINDOW = 7         # 均线用最近几根 K 线（7 是幸运数字）

THEMES = {
    "light": dict(bg="#ffffff", border="#d0d7de", text="#1f2328", muted="#656d76", grid="#eaeef2",
                  up="#1a7f37", down="#cf222e", ma="#8250df", vol_up="#1a7f3740", vol_down="#cf222e40"),
    "dark": dict(bg="#0d1117", border="#30363d", text="#e6edf3", muted="#8d96a0", grid="#21262d",
                 up="#3fb950", down="#f85149", ma="#d2a8ff", vol_up="#3fb95040", vol_down="#f8514940"),
}

W, H = 860, 360
PAD_L, PAD_R, PAD_T = 24, 64, 86
PRICE_H, GAP, VOL_H = 170, 14, 50
CYCLE = 14.0          # 一个动画循环的秒数
DRAW_END = 0.55       # 前 55% 时间逐根画出 K 线
FADE_START = 0.94     # 最后 6% 时间淡出，然后重新开始


# ---------------------------------------------------------------- 数据
def fetch_contributions(user: str, token: str) -> list[tuple[str, int]]:
    query = """query($login:String!){user(login:$login){contributionsCollection{
      contributionCalendar{weeks{contributionDays{date contributionCount}}}}}}"""
    req = urllib.request.Request(
        "https://api.github.com/graphql",
        data=json.dumps({"query": query, "variables": {"login": user}}).encode(),
        headers={"Authorization": f"bearer {token}", "Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req) as resp:
        payload = json.load(resp)
    weeks = payload["data"]["user"]["contributionsCollection"]["contributionCalendar"]["weeks"]
    return [(d["date"], d["contributionCount"]) for w in weeks for d in w["contributionDays"]]


def demo_contributions(seed: int = 7) -> list[tuple[str, int]]:
    rng = random.Random(seed)
    start = dt.date.today() - dt.timedelta(days=370)
    start -= dt.timedelta(days=(start.weekday() + 1) % 7)  # 从周日开始，和 GitHub 一致
    days, level = [], 2.0
    for i in range(371):
        level = max(0.0, level + rng.gauss(0, 0.6) + (1.5 if rng.random() < 0.04 else 0))
        level *= 0.97
        count = 0 if rng.random() < 0.35 else int(rng.expovariate(1 / (1 + level)))
        days.append(((start + dt.timedelta(days=i)).isoformat(), count))
    return days


def to_candles(days: list[tuple[str, int]]) -> list[dict]:
    counts = [c for _, c in days]
    price = [sum(counts[max(0, i - 6):i + 1]) for i in range(len(counts))]
    candles = []
    for i in range(0, len(days) - len(days) % 7 or len(days), 7):
        week = price[i:i + 7]
        if not week:
            continue
        candles.append(dict(date=days[i][0], o=week[0], c=week[-1], h=max(week), l=min(week),
                            v=sum(counts[i:i + 7])))
    for i, k in enumerate(candles):
        window = candles[max(0, i - MA_WINDOW + 1):i + 1]
        k["ma"] = sum(x["c"] for x in window) / len(window)
    return candles[-52:]


# ---------------------------------------------------------------- 画图
def render(candles: list[dict], theme: str, animate: bool = True) -> str:
    t = THEMES[theme]
    n = len(candles)
    plot_w = W - PAD_L - PAD_R
    step = plot_w / n
    body_w = max(3.0, step * 0.62)
    hi = max(k["h"] for k in candles) or 1
    lo = min(k["l"] for k in candles)
    span = max(hi - lo, 1)
    hi, lo = hi + span * 0.08, max(0, lo - span * 0.08)
    vmax = max(k["v"] for k in candles) or 1
    vol_top = PAD_T + PRICE_H + GAP

    def y(p: float) -> float:
        return PAD_T + PRICE_H * (1 - (p - lo) / (hi - lo))

    def x(i: int) -> float:
        return PAD_L + step * (i + 0.5)

    last = candles[-1]
    prev = candles[-2]["c"] if n > 1 else last["o"]
    change = last["c"] - prev                     # 和上一周收盘比
    pct_text = f" ({change / prev * 100:+.1f}%)" if prev else ""
    up = change >= 0
    total = sum(k["v"] for k in candles)
    color = t["up"] if up else t["down"]
    arrow = "▲" if up else "▼"

    out = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}" '
           f'font-family="ui-monospace,SFMono-Regular,Menlo,Consolas,monospace">']

    # ---- 动画样式
    css = [".k,.v{transform-box:fill-box}", ".k{transform-origin:center}", ".v{transform-origin:bottom}"]
    if animate:
        for i in range(n):
            s = DRAW_END * i / n * 100
            e = min(s + 3, DRAW_END * 100 + 3)
            css.append(f"@keyframes a{i}{{0%,{s:.2f}%{{opacity:0;transform:scaleY(0)}}"
                       f"{e:.2f}%,{FADE_START*100:.0f}%{{opacity:1;transform:scaleY(1)}}100%{{opacity:0;transform:scaleY(1)}}}}")
            css.append(f".i{i}{{animation:a{i} {CYCLE}s linear infinite}}")
        css.append(f"@keyframes ma{{0%,5%{{stroke-dashoffset:1}}{DRAW_END*100+3:.0f}%,{FADE_START*100:.0f}%"
                   f"{{stroke-dashoffset:0;opacity:1}}100%{{stroke-dashoffset:0;opacity:0}}}}")
        css.append(f".ma{{stroke-dasharray:1;stroke-dashoffset:1;animation:ma {CYCLE}s linear infinite}}")
        css.append(f"@keyframes tag{{0%,{DRAW_END*100:.0f}%{{opacity:0}}{DRAW_END*100+4:.0f}%,{FADE_START*100:.0f}%"
                   f"{{opacity:1}}100%{{opacity:0}}}}")
        css.append(f".tag{{opacity:0;animation:tag {CYCLE}s linear infinite}}")
        css.append("@keyframes blink{0%,100%{opacity:1}50%{opacity:.2}}.live{animation:blink 1.2s ease-in-out infinite}")
    out.append(f"<style>{''.join(css)}</style>")

    # ---- 背景和标题
    out.append(f'<rect x="0.5" y="0.5" width="{W-1}" height="{H-1}" rx="10" fill="{t["bg"]}" stroke="{t["border"]}"/>')
    out.append(f'<text x="{PAD_L}" y="34" font-size="20" font-weight="700" fill="{t["text"]}">${TICKER}</text>')
    out.append(f'<text x="{PAD_L + 88}" y="34" font-size="12" fill="{t["muted"]}">GitHub Contributions · 7D rolling · weekly candles</text>')
    out.append(f'<circle class="live" cx="{W - PAD_R + 22}" cy="29" r="4" fill="{t["up"]}"/>')
    out.append(f'<text x="{W - PAD_R + 30}" y="33" font-size="11" fill="{t["muted"]}">LIVE</text>')
    out.append(f'<text x="{PAD_L}" y="64" font-size="26" font-weight="700" fill="{t["text"]}">{last["c"]:.2f}</text>')
    out.append(f'<text x="{PAD_L + 96}" y="64" font-size="14" font-weight="600" fill="{color}">'
               f'{arrow} {change:+.2f}{pct_text}  1W</text>')
    stats = f'52W H {max(k["h"] for k in candles)}  ·  L {min(k["l"] for k in candles)}  ·  VOL {total:,}'
    out.append(f'<text x="{W - PAD_R}" y="64" font-size="12" text-anchor="end" fill="{t["muted"]}">{escape(stats)}</text>')

    # ---- 网格和价格刻度
    for j in range(5):
        p = lo + (hi - lo) * j / 4
        yy = y(p)
        out.append(f'<line x1="{PAD_L}" x2="{W - PAD_R}" y1="{yy:.1f}" y2="{yy:.1f}" stroke="{t["grid"]}"/>')
        out.append(f'<text x="{W - PAD_R + 8}" y="{yy + 4:.1f}" font-size="10" fill="{t["muted"]}">{p:.0f}</text>')
    out.append(f'<line x1="{PAD_L}" x2="{W - PAD_R}" y1="{vol_top + VOL_H}" y2="{vol_top + VOL_H}" stroke="{t["grid"]}"/>')

    # ---- 月份标签
    seen = set()
    for i, k in enumerate(candles):
        month = dt.date.fromisoformat(k["date"]).strftime("%b")
        if month not in seen and i > 0:
            seen.add(month)
            out.append(f'<text x="{x(i):.1f}" y="{vol_top + VOL_H + 16}" font-size="10" text-anchor="middle" '
                       f'fill="{t["muted"]}">{month}</text>')
        seen.add(month)

    # ---- K 线和成交量
    for i, k in enumerate(candles):
        rising = k["c"] >= k["o"]
        col = t["up"] if rising else t["down"]
        top, bot = y(max(k["o"], k["c"])), y(min(k["o"], k["c"]))
        cls = f' class="k i{i}"' if animate else ""
        out.append(f'<g{cls}><line x1="{x(i):.1f}" x2="{x(i):.1f}" y1="{y(k["h"]):.1f}" y2="{y(k["l"]):.1f}" '
                   f'stroke="{col}" stroke-width="1.2"/>'
                   f'<rect x="{x(i) - body_w / 2:.1f}" y="{top:.1f}" width="{body_w:.1f}" height="{max(bot - top, 1.2):.1f}" '
                   f'rx="1" fill="{col}"/></g>')
        vh = VOL_H * k["v"] / vmax
        vcls = f' class="v i{i}"' if animate else ""
        out.append(f'<rect{vcls} x="{x(i) - body_w / 2:.1f}" y="{vol_top + VOL_H - vh:.1f}" width="{body_w:.1f}" '
                   f'height="{max(vh, 0.5):.1f}" fill="{t["vol_up"] if rising else t["vol_down"]}"/>')

    # ---- 均线
    pts = " ".join(f"{x(i):.1f},{y(k['ma']):.1f}" for i, k in enumerate(candles))
    macls = ' class="ma" pathLength="1"' if animate else ""
    out.append(f'<polyline{macls} points="{pts}" fill="none" stroke="{t["ma"]}" stroke-width="1.6" '
               f'stroke-linejoin="round" stroke-linecap="round"/>')
    out.append(f'<text x="{PAD_L}" y="{PAD_T - 6}" font-size="10" fill="{t["ma"]}">MA{MA_WINDOW}</text>')

    # ---- 最新价标签
    tagcls = ' class="tag"' if animate else ""
    yl = y(last["c"])
    out.append(f'<g{tagcls}><line x1="{PAD_L}" x2="{W - PAD_R}" y1="{yl:.1f}" y2="{yl:.1f}" stroke="{color}" '
               f'stroke-dasharray="3 3" stroke-width="1"/>'
               f'<rect x="{W - PAD_R + 2}" y="{yl - 9:.1f}" width="{PAD_R - 8}" height="18" rx="3" fill="{color}"/>'
               f'<text x="{W - PAD_R + 2 + (PAD_R - 8) / 2}" y="{yl + 4:.1f}" font-size="11" font-weight="700" '
               f'text-anchor="middle" fill="{t["bg"]}">{last["c"]}</text></g>')

    out.append(f'<text x="{PAD_L}" y="{vol_top - 2}" font-size="10" fill="{t["muted"]}">VOL</text>')
    out.append("</svg>")
    return "\n".join(out)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--user", default=os.environ.get("GITHUB_USER", "yewenyiywy"))
    ap.add_argument("--out", default="dist")
    ap.add_argument("--demo", action="store_true", help="用模拟数据生成预览")
    ap.add_argument("--static", action="store_true", help="不带动画（调试用）")
    args = ap.parse_args()

    days = demo_contributions() if args.demo else fetch_contributions(args.user, os.environ["GITHUB_TOKEN"])
    candles = to_candles(days)
    os.makedirs(args.out, exist_ok=True)
    for theme, name in (("light", "kline.svg"), ("dark", "kline-dark.svg")):
        with open(os.path.join(args.out, name), "w", encoding="utf-8") as f:
            f.write(render(candles, theme, animate=not args.static))
    print(f"wrote {len(candles)} candles to {args.out}/")


if __name__ == "__main__":
    main()
