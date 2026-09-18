"""Small-multiples build: top-12 WRs per season, 2021-2025, 60 player-seasons.

Five seasons on one scatter would need five categorical hues; the palette caps
all-pairs forms (scatter) at three slots, so this facets into five single-hue
panels on shared axes instead -- the documented remedy.

    python build_chart.py [output.html]

Reads the rowset from data.py rather than BigQuery, so it renders offline.
See README.md before trusting the numbers: that rowset predates the exact
route counts and needs refreshing from query.sql.
"""
import json
import os
import sys

from data import ROWS

SEASONS = [2021, 2022, 2023, 2024, 2025]
# per-season least squares + pearson r (computed from the same rows)
FIT = {
    2021: (0.1569,  0.133, 0.856),
    2022: (0.1002,  1.198, 0.472),
    2023: (0.1964, -0.149, 0.732),
    2024: (0.0636,  1.571, 0.395),
    2025: (0.2543, -0.905, 0.802),
}

W, H = 340, 252
M = {"t": 12, "r": 16, "b": 34, "l": 40}
PW, PH = W - M["l"] - M["r"], H - M["t"] - M["b"]
X_MIN, X_MAX = 10.0, 22.0
Y_MIN, Y_MAX = 1.5, 4.75
XT, YT = [12, 16, 20], [2, 3, 4]
R = 4.5
FS = 11.0


def sx(v): return M["l"] + (v - X_MIN) / (X_MAX - X_MIN) * PW
def sy(v): return M["t"] + (Y_MAX - v) / (Y_MAX - Y_MIN) * PH


def text_w(s, fs=FS):
    narrow, wide = set("iljt.'!I "), set("MWmw")
    t = 0.0
    for ch in s:
        t += 0.30 if ch in narrow else 0.82 if ch in wide else 0.64 if ch.isupper() else 0.52
    return t * fs


def overlaps(a, b, pad=4.0):
    return not (a["x1"] + pad <= b["x0"] or b["x1"] + pad <= a["x0"]
                or a["y1"] + pad <= b["y0"] or b["y1"] + pad <= a["y0"])


flat = []          # flat list for the tooltip payload / table
for r in ROWS:
    season, rk, name, team, g, half, ppg, yprr, routes, tgt, ryds = r
    flat.append({"season": season, "rk": rk, "name": name, "team": team, "games": g,
                 "half": half, "ppg": ppg, "yprr": yprr, "routes": routes,
                 "targets": tgt, "ryds": ryds})

panels = []
gi = 0             # global index, matches `flat` order
issues = 0
for season in SEASONS:
    rows = [f for f in flat if f["season"] == season]
    slope, inter, rval = FIT[season]

    sv = [f'<svg viewBox="0 0 {W} {H}" role="img" aria-label="{season}: top 12 wide '
          f'receivers, half-PPR points per game against estimated yards per route run." '
          f'preserveAspectRatio="xMidYMid meet">']

    for yv in YT:
        yy = sy(yv)
        sv.append(f'<line class="grid" x1="{M["l"]}" y1="{yy:.1f}" x2="{W-M["r"]}" y2="{yy:.1f}"/>')
        sv.append(f'<text class="tick ty" x="{M["l"]-8}" y="{yy+3.5:.1f}">{yv}</text>')
    for xv in XT:
        xx = sx(xv)
        sv.append(f'<line class="grid" x1="{xx:.1f}" y1="{M["t"]}" x2="{xx:.1f}" y2="{H-M["b"]}"/>')
        sv.append(f'<text class="tick tx" x="{xx:.1f}" y="{H-M["b"]+17}">{xv}</text>')

    sv.append(f'<line class="axis" x1="{M["l"]}" y1="{H-M["b"]}" x2="{W-M["r"]}" y2="{H-M["b"]}"/>')
    sv.append(f'<line class="axis" x1="{M["l"]}" y1="{M["t"]}" x2="{M["l"]}" y2="{H-M["b"]}"/>')

    # per-panel trend, clipped to the shared y-range
    pa, pb = (X_MIN, slope * X_MIN + inter), (X_MAX, slope * X_MAX + inter)
    def clip(p0, p1):
        (x0, y0), (x1, y1) = p0, p1
        for lim, lo in ((Y_MIN, True), (Y_MAX, False)):
            if (y0 < lim) != (y1 < lim):
                t = (lim - y0) / (y1 - y0)
                xm = x0 + t * (x1 - x0)
                if (y0 < lim) if lo else (y0 > lim):
                    x0, y0 = xm, lim
                else:
                    x1, y1 = xm, lim
        return (x0, y0), (x1, y1)
    (cx0, cy0), (cx1, cy1) = clip(pa, pb)
    sv.append(f'<line class="trend" x1="{sx(cx0):.1f}" y1="{sy(cy0):.1f}" '
              f'x2="{sx(cx1):.1f}" y2="{sy(cy1):.1f}"/>')

    # selective labels: the season's top scorer and its efficiency leader
    top = min(rows, key=lambda d: d["rk"])
    eff = max(rows, key=lambda d: d["yprr"])
    marked = [top] if top is eff else [top, eff]

    boxes = [{"x0": sx(d["ppg"]) - R - 2, "x1": sx(d["ppg"]) + R + 2,
              "y0": sy(d["yprr"]) - R - 2, "y1": sy(d["yprr"]) + R + 2} for d in rows]
    # y-axis tick labels are ink too -- a label must not sit on top of them
    tick_boxes = [{"x0": M["l"] - 8 - 8, "x1": M["l"] - 8,
                   "y0": sy(v) - 5, "y1": sy(v) + 5} for v in YT]
    placed = []
    GAP = R + 5
    CAND = [(GAP, 3.8, "start"), (-GAP, 3.8, "end"), (0, -GAP - 3, "middle"),
            (0, GAP + 9, "middle"), (GAP, -GAP, "start"), (-GAP, -GAP, "end"),
            (GAP, GAP + 9, "start"), (-GAP, GAP + 9, "end"),
            (0, -GAP - 14, "middle"), (0, GAP + 20, "middle")]
    for d in marked:
        cx, cy = sx(d["ppg"]), sy(d["yprr"])
        w = text_w(d["name"])
        mine = next(i for i, q in enumerate(rows) if q is d)
        others = [b for k, b in enumerate(boxes) if k != mine]
        got = None
        for dx, dy, anc in CAND:
            tx, ty = cx + dx, cy + dy
            x0 = tx if anc == "start" else tx - w if anc == "end" else tx - w / 2
            bx = {"x0": x0, "x1": x0 + w, "y0": ty - FS * .78, "y1": ty + FS * .28}
            if bx["x0"] < 2 or bx["x1"] > W - 2:      continue
            if bx["y0"] < M["t"] - 6 or bx["y1"] > H - M["b"] + 4: continue
            if any(overlaps(bx, o) for o in others):  continue
            if any(overlaps(bx, q) for q in placed):  continue
            got = (tx, ty, anc, bx); break
        if got is None:
            print(f"  !! no slot for {d['name']} {season}")
            issues += 1
            continue
        tx, ty, anc, bx = got
        placed.append(bx)
        d["_label"] = (tx, ty, anc)

    for d in rows:
        sv.append(f'<circle class="dot" cx="{sx(d["ppg"]):.1f}" cy="{sy(d["yprr"]):.1f}" r="{R}"/>')
    for d in marked:
        if "_label" in d:
            tx, ty, anc = d["_label"]
            sv.append(f'<text class="plabel" x="{tx:.1f}" y="{ty:.1f}" '
                      f'text-anchor="{anc}">{d["name"]}</text>')
    for d in rows:
        idx = flat.index(d)
        sv.append(f'<circle class="hit" cx="{sx(d["ppg"]):.1f}" cy="{sy(d["yprr"]):.1f}" '
                  f'r="12" tabindex="0" data-i="{idx}"><title>{d["name"]}</title></circle>')
    sv.append("</svg>")

    panels.append(f'''      <figure class="panel">
        <figcaption><span class="pyear">{season}</span><span class="pr">r = {rval:.2f}</span></figcaption>
{chr(10).join(sv)}
      </figure>''')

print(f"panels: {len(panels)} | points: {len(flat)} | label issues: {issues}")

trs = []
for i, d in enumerate(flat):
    first = " season-start" if d["rk"] == 1 else ""
    trs.append(
        f'<tr class="r{first}"><td class="n yr">{d["season"] if d["rk"]==1 else ""}</td>'
        f'<td class="rank">{d["rk"]}</td><td class="nm">{d["name"]}</td><td>{d["team"]}</td>'
        f'<td class="n">{d["games"]}</td><td class="n">{d["half"]:.1f}</td>'
        f'<td class="n">{d["ppg"]:.2f}</td><td class="n">{d["yprr"]:.2f}</td>'
        f'<td class="n">{d["routes"]:,}</td><td class="n">{d["targets"]}</td>'
        f'<td class="n">{d["ryds"]:,}</td></tr>')
rows_html = "\n".join(trs)
payload = json.dumps(flat)

html = f"""<title>WR Volume vs Efficiency</title>
<style>
  :root {{
    color-scheme: light;
    --plane:#f9f9f7; --surface:#fcfcfb;
    --ink:#0b0b0b; --ink-2:#52514e; --ink-3:#898781;
    --grid:#e1e0d9; --axis:#c3c2b7; --rule:rgba(11,11,11,.10);
    --series:#2a78d6;
    --sans: system-ui,-apple-system,"Segoe UI",sans-serif;
    --mono: ui-monospace,SFMono-Regular,Menlo,Consolas,monospace;
  }}
  @media (prefers-color-scheme: dark) {{
    :root:not([data-theme="light"]) {{
      color-scheme: dark;
      --plane:#0d0d0d; --surface:#1a1a19;
      --ink:#ffffff; --ink-2:#c3c2b7; --ink-3:#898781;
      --grid:#2c2c2a; --axis:#383835; --rule:rgba(255,255,255,.10);
      --series:#3987e5;
    }}
  }}
  :root[data-theme="dark"] {{
    color-scheme: dark;
    --plane:#0d0d0d; --surface:#1a1a19;
    --ink:#ffffff; --ink-2:#c3c2b7; --ink-3:#898781;
    --grid:#2c2c2a; --axis:#383835; --rule:rgba(255,255,255,.10);
    --series:#3987e5;
  }}

  *,*::before,*::after {{ box-sizing:border-box; }}
  body {{ margin:0; background:var(--plane); color:var(--ink);
          font-family:var(--sans); line-height:1.55; -webkit-font-smoothing:antialiased; }}
  .wrap {{ max-width:1060px; margin:0 auto; padding:40px 24px 72px;
           display:flex; flex-direction:column; gap:26px; }}

  header {{ display:flex; flex-direction:column; gap:9px; }}
  .eyebrow {{ font-family:var(--mono); font-size:11.5px; letter-spacing:.10em;
              text-transform:uppercase; color:var(--ink-3); }}
  h1 {{ margin:0; font-size:29px; font-weight:640; letter-spacing:-.015em; text-wrap:balance; }}
  .lede {{ margin:0; max-width:70ch; color:var(--ink-2); font-size:15px; }}
  .lede strong {{ color:var(--ink); font-weight:600; }}

  .card {{ background:var(--surface); border:1px solid var(--rule);
           border-radius:10px; padding:20px; }}
  .axis-note {{ display:flex; justify-content:space-between; gap:16px; flex-wrap:wrap;
                font-size:12.5px; color:var(--ink-2); margin-bottom:14px; }}
  .axis-note span {{ display:inline-flex; align-items:center; gap:7px; }}
  .axis-note i {{ font-style:normal; font-family:var(--mono); font-size:11px;
                  color:var(--ink-3); }}

  .grid-panels {{ display:grid; gap:16px;
                  grid-template-columns:repeat(auto-fit,minmax(288px,1fr)); }}
  .panel {{ margin:0; display:flex; flex-direction:column; gap:4px; }}
  figcaption {{ display:flex; align-items:baseline; justify-content:space-between;
                padding:0 2px; }}
  .pyear {{ font-family:var(--mono); font-size:12.5px; font-weight:500; color:var(--ink); }}
  .pr {{ font-family:var(--mono); font-size:11px; color:var(--ink-3); }}
  svg {{ display:block; width:100%; height:auto; }}

  .grid {{ stroke:var(--grid); stroke-width:1; }}
  .axis {{ stroke:var(--axis); stroke-width:1; }}
  .trend {{ stroke:var(--axis); stroke-width:1; }}
  .tick {{ font-family:var(--mono); font-size:9.5px; fill:var(--ink-3); }}
  .ty {{ text-anchor:end; }} .tx {{ text-anchor:middle; }}
  .dot {{ fill:var(--series); stroke:var(--surface); stroke-width:1.5; }}
  .plabel {{ font-family:var(--sans); font-size:11px; fill:var(--ink-2); pointer-events:none; }}
  .hit {{ fill:transparent; cursor:pointer; outline:none; }}
  .hit:focus-visible {{ stroke:var(--ink); stroke-width:2; }}

  .tip {{ position:fixed; z-index:20; pointer-events:none; opacity:0;
          transition:opacity .12s ease; background:var(--surface);
          border:1px solid var(--rule); border-radius:8px; padding:10px 12px;
          box-shadow:0 6px 22px rgba(0,0,0,.16); min-width:190px; }}
  @media (prefers-reduced-motion: reduce) {{ .tip {{ transition:none; }} }}
  .tip.on {{ opacity:1; }}
  .tip h4 {{ margin:0 0 2px; font-size:13.5px; font-weight:640; }}
  .tip .sub {{ font-family:var(--mono); font-size:11px; color:var(--ink-3); margin-bottom:7px; }}
  .tip dl {{ margin:0; display:grid; grid-template-columns:auto auto; gap:2px 14px; }}
  .tip dt {{ font-size:12px; color:var(--ink-2); }}
  .tip dd {{ margin:0; font-family:var(--mono); font-size:12px; text-align:right;
             font-variant-numeric:tabular-nums; }}

  h2 {{ margin:0 0 2px; font-size:15px; font-weight:620; letter-spacing:-.005em; }}
  .table-scroll {{ overflow-x:auto; }}
  table {{ border-collapse:collapse; width:100%; font-size:12.5px; }}
  caption {{ text-align:left; color:var(--ink-2); font-size:13px; padding-bottom:12px; }}
  th,td {{ padding:5px 9px; border-bottom:1px solid var(--rule); white-space:nowrap; }}
  thead th {{ font-family:var(--mono); font-size:10px; letter-spacing:.06em;
              text-transform:uppercase; color:var(--ink-3); font-weight:500;
              text-align:right; border-bottom-color:var(--axis); }}
  thead th:nth-child(-n+4) {{ text-align:left; }}
  tr.season-start td {{ border-top:1px solid var(--axis); }}
  tbody tr:first-child td {{ border-top:none; }}
  tbody tr:last-child td {{ border-bottom:none; }}
  .yr {{ font-family:var(--mono); color:var(--ink); font-weight:500; text-align:left; }}
  .rank {{ font-family:var(--mono); color:var(--ink-3); }}
  .nm {{ font-weight:530; }}
  td.n {{ font-family:var(--mono); text-align:right; font-variant-numeric:tabular-nums; }}

  .note {{ font-size:13px; color:var(--ink-2); max-width:72ch; }}
  .note strong {{ color:var(--ink); font-weight:600; }}

  /* ---- print / PDF ---------------------------------------------------- */
  @page {{ size: Letter portrait; margin: 14mm 13mm; }}
  @media print {{
    /* a dark-mode viewer must still print on white -- these selectors match
       the specificity of the dark blocks above and come later, so they win */
    :root, :root[data-theme="dark"], :root:not([data-theme="light"]) {{
      color-scheme: light;
      --plane:#ffffff; --surface:#ffffff;
      --ink:#0b0b0b; --ink-2:#45443f; --ink-3:#6f6d67;
      --grid:#dcdbd3; --axis:#a9a89f; --rule:rgba(11,11,11,.16);
      --series:#1c5cab;
    }}
    body {{ background:#fff; }}
    .wrap {{ max-width:none; padding:0; gap:16px; }}
    .card {{ border-radius:0; padding:0; border:none; }}
    .tip {{ display:none !important; }}

    h1 {{ font-size:20px; }}
    .lede {{ font-size:11.5px; max-width:none; }}
    .note {{ font-size:11px; max-width:none; }}
    header {{ gap:6px; }}
    .axis-note {{ margin-bottom:10px; font-size:11.5px; }}

    /* Two panels per row keeps the in-panel type readable in print; the width
       cap is what lets all three rows (five panels) share page one instead of
       orphaning 2025 onto page two. */
    .grid-panels {{ grid-template-columns:repeat(2,1fr); gap:9px;
                    max-width:614px; margin:0 auto; }}
    .panel + .panel {{ }}
    figcaption {{ padding:0; }}
    .pyear {{ font-size:11.5px; }} .pr {{ font-size:10px; }}
    .panel {{ break-inside:avoid; }}
    header, .axis-note {{ break-inside:avoid; }}
    .note {{ break-inside:avoid; }}

    h2 {{ break-after:avoid; }}
    .table-scroll {{ overflow:visible; }}
    table {{ font-size:9.5px; }}
    caption {{ font-size:11px; padding-bottom:8px; }}
    th, td {{ padding:2.6px 5px; }}
    thead {{ display:table-header-group; }}   /* repeat header on each page */
    tr {{ break-inside:avoid; }}
  }}
</style>

<div class="wrap">
  <header>
    <div class="eyebrow">2021–2025 · regular season only · half-PPR</div>
    <h1>Some years the top scorers are the efficient ones. Some years they aren't.</h1>
    <p class="lede">Every top-12 wide receiver season from the last five years — 60 in all,
      twelve per season — plotted by half-PPR points per game against yards per route run.
      Panels share both axes, so a point in one year sits where it would in any other.
      How tightly the two move together swings hard by season: <strong>2021</strong> and
      <strong>2025</strong> are strongly aligned (r&nbsp;=&nbsp;0.86, 0.80), while
      <strong>2022</strong> and <strong>2024</strong> nearly break the link
      (0.47, 0.40) — those were years the leading scorers won on volume.</p>
  </header>

  <div class="card">
    <div class="axis-note">
      <span><i>x</i> Half-PPR points per game</span>
      <span><i>y</i> Yards per route run (est.)</span>
      <span><i>line</i> Least-squares fit for that season</span>
    </div>
    <div class="grid-panels">
{chr(10).join(panels)}
    </div>
  </div>

  <div class="card">
    <h2>All sixty player-seasons</h2>
    <div class="table-scroll">
      <table>
        <caption>Top 12 by half-PPR points within each season, 2021–2025 regular seasons.
          Every plotted value appears here.</caption>
        <thead>
          <tr><th>Yr</th><th>#</th><th>Player</th><th>Tm</th><th>G</th><th>½PPR</th>
            <th>PPG</th><th>YPRR</th><th>Routes</th><th>Tgt</th><th>Rec yds</th></tr>
        </thead>
        <tbody>
{rows_html}
        </tbody>
      </table>
    </div>
  </div>

  <p class="note"><strong>Scope.</strong> Regular season only, throughout — scoring, games,
    routes and receiving yards all exclude playoff games. This matters for the efficiency
    figure: pooling postseason games inflates a contender's route count without the reader
    seeing it. Puka Nacua's 2025 is the clearest case — 409 routes on regular-season play
    against 513 including the Rams' postseason, which moves his YPRR from 4.19 to 3.99.</p>

  <p class="note"><strong>Scoring.</strong> Half&#8209;PPR: standard scoring plus 0.5 per
    reception, computed as <code>fantasy_points + 0.5 × receptions</code>.</p>

  <p class="note"><strong>On the YPRR figure.</strong> Routes are estimated, not charted:
    <code>routes ≈ offensive snap share × team dropbacks</code>, where team dropbacks are
    pass attempts plus sacks taken. That assumes a receiver runs a route on every dropback
    he's on the field for, so it overstates routes — and understates YPRR — for receivers
    who stay in to block. Use it to compare within a position group, not as a precise
    value. Charted routes are a paid PFF product.</p>
</div>

<div class="tip" id="tip" role="status" aria-live="polite"></div>

<script>
  const DATA = {payload};
  const tip = document.getElementById('tip');
  const fmt = new Intl.NumberFormat('en-US');
  function show(el) {{
    const d = DATA[+el.dataset.i];
    tip.innerHTML =
      '<h4>' + d.name + '</h4>' +
      '<div class="sub">' + d.season + ' · ' + d.team + ' · WR' + d.rk + ' · ' + d.games + ' g</div>' +
      '<dl>' +
        '<dt>½PPR/game</dt><dd>' + d.ppg.toFixed(2) + '</dd>' +
        '<dt>YPRR (est.)</dt><dd>' + d.yprr.toFixed(2) + '</dd>' +
        '<dt>Total ½PPR</dt><dd>' + d.half.toFixed(1) + '</dd>' +
        '<dt>Routes (est.)</dt><dd>' + fmt.format(d.routes) + '</dd>' +
        '<dt>Targets</dt><dd>' + d.targets + '</dd>' +
        '<dt>Rec yards</dt><dd>' + fmt.format(d.ryds) + '</dd>' +
      '</dl>';
    const r = el.getBoundingClientRect();
    tip.classList.add('on');
    const tr = tip.getBoundingClientRect();
    let x = r.left + r.width / 2 - tr.width / 2;
    let y = r.top - tr.height - 10;
    if (y < 8) y = r.bottom + 10;
    x = Math.max(8, Math.min(x, window.innerWidth - tr.width - 8));
    tip.style.left = x + 'px'; tip.style.top = y + 'px';
  }}
  function hide() {{ tip.classList.remove('on'); }}
  document.querySelectorAll('.hit').forEach(el => {{
    el.addEventListener('mouseenter', () => show(el));
    el.addEventListener('mouseleave', hide);
    el.addEventListener('focus', () => show(el));
    el.addEventListener('blur', hide);
  }});
</script>
"""

out = sys.argv[1] if len(sys.argv) > 1 else os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "wr_chart.html")
with open(out, "w") as f:
    f.write(html)
print("wrote", out)
