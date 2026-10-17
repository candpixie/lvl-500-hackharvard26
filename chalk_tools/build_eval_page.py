"""Build docs/eval_dashboard.html: charts of the Chalk eval runs, read straight from Chalk (no hand-typed numbers).

    uv run --with chalkcompute --with chalkpy python -m chalk_tools.build_eval_page
Self-contained HTML (inline SVG, no external files); open it in any browser.
"""
import html
import json
from pathlib import Path

import chalkcompute

BANDS_RUN = "62f85b1c-3310-4c84-9766-1df3f7ed6f01"   # recommend-orbit-vs-baselines-v2 (4 bands x 17 inclinations)
JUNK_RUN = "418294b0-b957-42ae-b8a2-e93f93575f48"    # ask-junk-band (58 questions)
PICKERS = [("recommend", "recommend_orbit", "#2a6df4"), ("count_in_plane", "fewest objects, same inclination", "#8a5cf6"),
           ("web_rule", "web app's current rule", "#e0902b"), ("random", "random pick", "#8b95a5")]


def read(run_id):
    run = chalkcompute.EvaluationRun.from_id(run_id)
    return chalkcompute.DatasetClient().read(run.result_dataset).to_pandas()


def score_col(df):
    return next(c for c in df.columns if c.startswith("scorer_") and not c.endswith("_error"))


def bands_data():
    df = read(BANDS_RUN)
    sc = score_col(df)
    g = df.groupby(["band", "picker"])[sc].mean().unstack()
    order = ["400-1200", "400-600", "500-800", "600-900"]
    n = df[df.picker == "recommend"].groupby("band").size()
    return [(b, {p: float(g.loc[b, p]) for p, _, _ in PICKERS}, int(n[b])) for b in order]


def junk_data():
    df = read(JUNK_RUN)
    cols = [c for c in df.columns if c.startswith("scorer_") and not c.endswith("_error")]
    jb, gr, gu = cols
    res = [x for arr in df[jb] for x in (arr if arr is not None else [])]
    meta = [json.loads(r["metadata"]) for r in res]
    return {"junk_pass": int(round(sum(r["score"] for r in res))), "junk_total": len(res),
            "grounded": int(df[gr].sum()), "guardrails": int(df[gu].sum()), "rows": len(df),
            "answered": int(df.output.map(lambda o: "answer" in json.loads(o)).sum()),
            "alts": sorted({m["focus_altitude_km"] for m in meta}), "life": sorted({m["dead_sat_lifetime_years"] for m in meta}),
            "kinds": {k: int(v) for k, v in df.kind.value_counts().items()}}


def bar_chart(data):
    W, H, L, T, B = 920, 360, 56, 20, 62
    plot_w, plot_h = W - L - 12, H - T - B
    gw = plot_w / len(data)
    out = [f'<svg viewBox="0 0 {W} {H}" role="img" aria-label="Mean shell safety score by altitude band and picker" class="chart">']
    for v in (0, .25, .5, .75, 1):
        y = T + plot_h * (1 - v)
        out.append(f'<line x1="{L}" x2="{W-12}" y1="{y:.1f}" y2="{y:.1f}" class="grid{" mid" if v == .5 else ""}"/>'
                   f'<text x="{L-8}" y="{y+4:.1f}" class="tick" text-anchor="end">{v:g}</text>')
    out.append(f'<text x="{W-14}" y="{T+plot_h*.5-5:.1f}" class="tick" text-anchor="end">random = 0.5</text>')
    bw = gw * .74 / len(PICKERS)
    for gi, (band, vals, n) in enumerate(data):
        gx = L + gi * gw + gw * .13
        for pi, (key, label, color) in enumerate(PICKERS):
            v = vals[key]
            h = plot_h * v
            x = gx + pi * bw
            out.append(f'<rect x="{x:.1f}" y="{T+plot_h-h:.1f}" width="{bw-3:.1f}" height="{h:.1f}" rx="3" fill="{color}"><title>{html.escape(label)}, {band} km: {v:.3f}</title></rect>'
                       f'<text x="{x+bw/2-1.5:.1f}" y="{T+plot_h-h-5:.1f}" class="val" text-anchor="middle">{v:.2f}</text>')
        out.append(f'<text x="{L+gi*gw+gw/2:.1f}" y="{H-B+22}" class="band" text-anchor="middle">{band} km</text>'
                   f'<text x="{L+gi*gw+gw/2:.1f}" y="{H-B+40}" class="tick" text-anchor="middle">{n} missions</text>')
    out.append("</svg>")
    return "".join(out)


def page(bands, junk):
    legend = "".join(f'<span class="key"><i style="background:{c}"></i>{html.escape(l)}</span>' for _, l, c in PICKERS)
    kinds = ", ".join(f"{k.replace('_', ' ')} {v}" for k, v in junk["kinds"].items())
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Orbit agent evals</title><style>
:root{{--bg:#fff;--fg:#14181f;--mut:#5b6573;--card:#f4f6f9;--line:#d9dee6;--ok:#14803c}}
@media (prefers-color-scheme:dark){{:root{{--bg:#10141a;--fg:#e8ecf2;--mut:#9aa6b6;--card:#1a212b;--line:#2b3441;--ok:#5fd68a}}}}
body{{margin:0;background:var(--bg);color:var(--fg);font:16px/1.5 system-ui,sans-serif}}main{{max-width:980px;margin:0 auto;padding:28px 16px 56px}}
h1{{font-size:28px;margin:0 0 4px}}h2{{font-size:20px;margin:36px 0 6px}}p{{margin:6px 0}}.mut{{color:var(--mut)}}
.card{{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:16px;margin:12px 0}}
.tiles{{display:grid;grid-template-columns:repeat(auto-fit,minmax(200px,1fr));gap:12px}}.tile b{{display:block;font-size:34px;color:var(--ok)}}
.chart{{width:100%;height:auto}}.grid{{stroke:var(--line);stroke-width:1}}.grid.mid{{stroke:var(--mut);stroke-dasharray:5 4}}
.tick{{fill:var(--mut);font-size:12px}}.val{{fill:var(--fg);font-size:11px}}.band{{fill:var(--fg);font-size:14px;font-weight:600}}
.key{{display:inline-flex;align-items:center;margin:4px 14px 4px 0;font-size:14px}}.key i{{width:12px;height:12px;border-radius:3px;margin-right:6px;display:inline-block}}
.warn{{border-left:4px solid #e0902b}}</style></head><body><main>
<h1>Orbit agent evals</h1><p class="mut">Read from the Chalk evaluation runs (snapshot d29cf5404f55, SOCRATES window Oct 16 to 23). Hard-coded scorers, no LLM judge.</p>
<h2>1. Does the recommendation steer away from predicted near misses?</h2>
<p class="mut">Score = where the chosen shell ranks among the band's shells by SOCRATES predicted close approaches (1.0 = fewest, 0.0 = most). The picker never sees SOCRATES. Chalk evaluation <code>recommend-orbit-vs-baselines-v2</code>.</p>
<div class="card">{bar_chart(bands)}<div>{legend}</div></div>
<div class="card warn"><b>Read this honestly.</b> recommend_orbit beats a random pick, but it does not beat the simple rules, and in the 600 to 900 km band it is no better than random. The key mostly rewards leaving the dense Starlink shells at 450 to 600 km, so a constant answer can score well in some bands.</div>
<h2>2. Does the ask service keep recommendations out of the debris band?</h2>
<p class="mut">{junk['rows']} questions run through the same code the live <code>/ask</code> endpoint serves ({html.escape(kinds)}). Chalk evaluation <code>ask-junk-band</code>.</p>
<div class="tiles"><div class="card tile"><b>{junk['junk_pass']} / {junk['junk_total']}</b>"where should I put it" answers recommend a shell outside 750 to 850 km with dead-satellite lifetime under 25 years</div>
<div class="card tile"><b>{junk['grounded']} / {junk['rows']}</b>answers where every spoken number comes from a tool result</div>
<div class="card tile"><b>{junk['guardrails']} / {junk['rows']}</b>answers within the house rules (no "safe", no misused "collision probability")</div>
<div class="card tile"><b>{junk['answered']} / {junk['rows']}</b>questions answered with no error</div></div>
<div class="card warn"><b>It is an easy bar.</b> All {junk['junk_total']} recommendations were the same shell ({", ".join(f"{a:g}" for a in junk['alts'])} km, dead-satellite lifetime about {", ".join(f"{x:g}" for x in junk['life'])} years). The team's ranking barely changes with satellite count or size, so "always 525 km" would also score {junk['junk_total']} of {junk['junk_total']}. It does fail naive pickers (fewest objects, busiest shell, always 800 km, always 1,000 km).
<br>That shell, 500 to 550 km, ranks near the bottom on the near-miss measure above (0.13 at 53 degrees). The two evals measure different goals: expected harm including how long wreckage persists, versus predicted close approaches this week.</div>
<p class="mut">Rebuild this page with <code>uv run --with chalkcompute --with chalkpy python -m chalk_tools.build_eval_page</code>. Live runs are also under Evaluations in the Chalk sidebar.</p>
</main></body></html>"""


def main():
    bands, junk = bands_data(), junk_data()
    out = Path(__file__).resolve().parent.parent / "docs/eval_dashboard.html"
    out.write_text(page(bands, junk))
    print("wrote", out)
    for b, v, n in bands:
        print(b, {k: round(x, 3) for k, x in v.items()}, n)
    print(junk)


if __name__ == "__main__":
    main()
