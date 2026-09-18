"""SUPERSEDED -- kept for the label-placement routine, not for its numbers.

The first iteration: 2025 only, full PPR, one panel. ../build_chart.py replaced
it with five seasons of half PPR as small multiples.

Its embedded PLAYERS rowset is wrong twice over and is NOT worth rescuing:
regular season and postseason are pooled (Nacua's 513 routes and 2047 yards
span both), and the routes are snap-share estimates rather than counted. Both
were fixed later -- see ../README.md. Do not copy numbers out of this file.

Label placement is done programmatically: 12 labels on a 12-point scatter
collide badly when placed by hand, so each label tries candidate offsets in
preference order and takes the first that clears every dot, every already-placed
label, and the plot bounds. That part is still good, and is why this is here.

    python single_season_2025.py [output.html]
"""

import os
import sys

# name, team, games, total_ppr, ppg, yprr, routes, targets, rec_yards
PLAYERS = [
    ("Puka Nacua",         "LA",  16, 375.0, 23.44, 3.990, 513, 208, 2047),
    ("Jaxon Smith-Njigba", "SEA", 17, 359.9, 21.17, 4.150, 480, 189, 1992),
    ("Amon-Ra St. Brown",  "DET", 17, 324.0, 19.06, 2.594, 540, 172, 1401),
    ("Ja'Marr Chase",      "CIN", 16, 313.6, 19.60, 2.319, 609, 185, 1412),
    ("George Pickens",     "DAL", 17, 291.9, 17.17, 2.637, 542, 137, 1429),
    ("Chris Olave",        "NO",  16, 268.0, 16.75, 2.289, 508, 156, 1163),
    ("Zay Flowers",        "BAL", 17, 243.3, 14.31, 2.968, 408, 118, 1211),
    ("Nico Collins",       "HOU", 15, 226.2, 15.08, 2.586, 440, 127, 1138),
    ("Davante Adams",      "LA",  14, 222.9, 15.92, 2.219, 439, 139,  974),
    ("Michael Wilson",     "ARI", 17, 220.6, 12.98, 1.723, 584, 126, 1006),
    ("A.J. Brown",         "PHI", 15, 220.3, 14.69, 2.216, 464, 128, 1028),
    ("Jameson Williams",   "DET", 17, 219.9, 12.94, 1.980, 564, 102, 1117),
]

W, H = 940, 580
M = {"t": 28, "r": 34, "b": 62, "l": 74}
PW = W - M["l"] - M["r"]
PH = H - M["t"] - M["b"]

X_MIN, X_MAX, X_STEP = 12.0, 24.0, 2.0
Y_MIN, Y_MAX, Y_STEP = 1.5, 4.5, 0.5

R = 6           # dot radius
FS = 12.5       # label font size
LH = 13.0       # label box height


def sx(v):
    return M["l"] + (v - X_MIN) / (X_MAX - X_MIN) * PW


def sy(v):
    return M["t"] + (Y_MAX - v) / (Y_MAX - Y_MIN) * PH


def text_w(s, fs=FS):
    """Approximate rendered width for system-ui at fs px."""
    narrow, wide = set("iljt.'!I "), set("MWmw")
    total = 0.0
    for ch in s:
        if ch in narrow:
            total += 0.30
        elif ch in wide:
            total += 0.82
        elif ch.isupper():
            total += 0.64
        else:
            total += 0.52
    return total * fs


def overlaps(a, b, pad=6.0):
    return not (
        a["x1"] + pad <= b["x0"]
        or b["x1"] + pad <= a["x0"]
        or a["y1"] + pad <= b["y0"]
        or b["y1"] + pad <= a["y0"]
    )


pts = []
for name, team, g, tot, ppg, yprr, routes, tgts, ryds in PLAYERS:
    pts.append({
        "name": name, "team": team, "games": g, "total": tot, "ppg": ppg,
        "yprr": yprr, "routes": routes, "targets": tgts, "ryds": ryds,
        "cx": sx(ppg), "cy": sy(yprr),
    })

# Dot obstacles (include the 2px surface ring)
dot_boxes = [
    {"x0": p["cx"] - R - 2, "x1": p["cx"] + R + 2,
     "y0": p["cy"] - R - 2, "y1": p["cy"] + R + 2}
    for p in pts
]

GAP = R + 6
# (dx, dy, anchor) in preference order
CANDIDATES = [
    (GAP, 4.5, "start"), (-GAP, 4.5, "end"),
    (0, -GAP - 4, "middle"), (0, GAP + 11, "middle"),
    (GAP, -GAP, "start"), (-GAP, -GAP, "end"),
    (GAP, GAP + 8, "start"), (-GAP, GAP + 8, "end"),
]

placed = []
for self_i, p in enumerate(pts):
    w = text_w(p["name"])
    chosen = None
    # a label is anchored to its own dot by design -- only other dots are obstacles
    others = [d for k, d in enumerate(dot_boxes) if k != self_i]
    for dx, dy, anchor in CANDIDATES:
        tx, ty = p["cx"] + dx, p["cy"] + dy
        if anchor == "start":
            x0 = tx
        elif anchor == "end":
            x0 = tx - w
        else:
            x0 = tx - w / 2
        box = {"x0": x0, "x1": x0 + w, "y0": ty - LH * 0.78, "y1": ty + LH * 0.28}

        if box["x0"] < M["l"] - 8 or box["x1"] > W - M["r"] + 8:
            continue
        if box["y0"] < M["t"] - 6 or box["y1"] > H - M["b"] + 6:
            continue
        if any(overlaps(box, d) for d in others):
            continue
        if any(overlaps(box, q["box"]) for q in placed):
            continue
        chosen = (tx, ty, anchor, box)
        break

    if chosen is None:  # last resort, still recorded so we can report it
        tx, ty, anchor = p["cx"] + GAP, p["cy"] + 4.5, "start"
        box = {"x0": tx, "x1": tx + w, "y0": ty - LH * 0.78, "y1": ty + LH * 0.28}
        print(f"  !! no clean slot for {p['name']}")
    tx, ty, anchor, box = chosen if chosen else (tx, ty, anchor, box)
    p.update(lx=tx, ly=ty, anchor=anchor, box=box)
    placed.append(p)

# ---- verify no collisions survived ----
issues = 0
for i, a in enumerate(placed):
    for b in placed[i + 1:]:
        if overlaps(a["box"], b["box"]):
            print(f"  !! label collision: {a['name']} / {b['name']}")
            issues += 1
    for j, d in enumerate(dot_boxes):
        if pts[j]["name"] == a["name"]:
            continue
        if overlaps(a["box"], d):
            print(f"  !! label over dot: {a['name']} / {pts[j]['name']}")
            issues += 1
print(f"label placement issues: {issues}")

# ---------------- SVG ----------------
sv = []
sv.append(f'<svg viewBox="0 0 {W} {H}" role="img" '
          f'aria-label="Scatter plot of 2025 top-12 fantasy wide receivers, '
          f'fantasy points per game against estimated yards per route run." '
          f'preserveAspectRatio="xMidYMid meet">')

# gridlines
y = Y_MIN
while y <= Y_MAX + 1e-9:
    yy = sy(y)
    sv.append(f'<line class="grid" x1="{M["l"]}" y1="{yy:.1f}" x2="{W-M["r"]}" y2="{yy:.1f}"/>')
    sv.append(f'<text class="tick ty" x="{M["l"]-12}" y="{yy+4:.1f}">{y:.1f}</text>')
    y += Y_STEP

x = X_MIN
while x <= X_MAX + 1e-9:
    xx = sx(x)
    sv.append(f'<line class="grid" x1="{xx:.1f}" y1="{M["t"]}" x2="{xx:.1f}" y2="{H-M["b"]}"/>')
    sv.append(f'<text class="tick tx" x="{xx:.1f}" y="{H-M["b"]+22}">{x:.0f}</text>')
    x += X_STEP

# axis rules
sv.append(f'<line class="axis" x1="{M["l"]}" y1="{H-M["b"]}" x2="{W-M["r"]}" y2="{H-M["b"]}"/>')
sv.append(f'<line class="axis" x1="{M["l"]}" y1="{M["t"]}" x2="{M["l"]}" y2="{H-M["b"]}"/>')

# least-squares trend line (r = 0.784 across these twelve) -- recessive hairline,
# solid per the mark spec; it is what makes the two outliers legible as outliers.
SLOPE, INTERCEPT = 0.1765, -0.348
tx0, ty0 = X_MIN, SLOPE * X_MIN + INTERCEPT
tx1, ty1 = X_MAX, SLOPE * X_MAX + INTERCEPT
sv.append(f'<line class="trend" x1="{sx(tx0):.1f}" y1="{sy(ty0):.1f}" '
          f'x2="{sx(tx1):.1f}" y2="{sy(ty1):.1f}"/>')
sv.append(f'<text class="trend-label" x="{sx(21.0):.1f}" '
          f'y="{sy(SLOPE*21.0+INTERCEPT)-9:.1f}" text-anchor="middle">trend</text>')

# axis titles
sv.append(f'<text class="axis-title" x="{M["l"]+PW/2:.1f}" y="{H-14}" text-anchor="middle">'
          f'Fantasy points per game (PPR)</text>')
sv.append(f'<text class="axis-title" x="{-(M["t"]+PH/2):.1f}" y="20" '
          f'text-anchor="middle" transform="rotate(-90)">Yards per route run (est.)</text>')

# marks
for i, p in enumerate(placed):
    sv.append(f'<circle class="dot" cx="{p["cx"]:.1f}" cy="{p["cy"]:.1f}" r="{R}"/>')
    sv.append(f'<text class="plabel" x="{p["lx"]:.1f}" y="{p["ly"]:.1f}" '
              f'text-anchor="{p["anchor"]}">{p["name"].replace("&","&amp;")}</text>')

# hover targets last so they sit on top; r=14 clears the 24px minimum
for i, p in enumerate(placed):
    sv.append(
        f'<circle class="hit" cx="{p["cx"]:.1f}" cy="{p["cy"]:.1f}" r="14" '
        f'tabindex="0" data-i="{i}"><title>{p["name"]}</title></circle>'
    )
sv.append("</svg>")
svg = "\n".join(sv)

rows = "\n".join(
    f'<tr><td class="rank">{i+1}</td><td class="nm">{p["name"]}</td><td>{p["team"]}</td>'
    f'<td class="n">{p["games"]}</td><td class="n">{p["total"]:.1f}</td>'
    f'<td class="n">{p["ppg"]:.2f}</td><td class="n">{p["yprr"]:.2f}</td>'
    f'<td class="n">{p["routes"]:,}</td><td class="n">{p["targets"]}</td>'
    f'<td class="n">{p["ryds"]:,}</td></tr>'
    for i, p in enumerate(pts)
)

import json
payload = json.dumps([
    {"name": p["name"], "team": p["team"], "games": p["games"], "total": p["total"],
     "ppg": p["ppg"], "yprr": p["yprr"], "routes": p["routes"],
     "targets": p["targets"], "ryds": p["ryds"]}
    for p in pts
])

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
  body {{
    margin:0; background:var(--plane); color:var(--ink);
    font-family:var(--sans); line-height:1.55;
    -webkit-font-smoothing:antialiased;
  }}
  .wrap {{ max-width:980px; margin:0 auto; padding:40px 24px 72px;
           display:flex; flex-direction:column; gap:26px; }}

  header {{ display:flex; flex-direction:column; gap:9px; }}
  .eyebrow {{ font-family:var(--mono); font-size:11.5px; letter-spacing:.10em;
              text-transform:uppercase; color:var(--ink-3); }}
  h1 {{ margin:0; font-size:29px; font-weight:640; letter-spacing:-.015em;
        text-wrap:balance; }}
  .lede {{ margin:0; max-width:66ch; color:var(--ink-2); font-size:15px; }}

  .card {{ background:var(--surface); border:1px solid var(--rule);
           border-radius:10px; padding:22px 20px 12px; }}
  .chart-scroll {{ overflow-x:auto; }}
  svg {{ display:block; width:100%; min-width:660px; height:auto; }}

  .grid {{ stroke:var(--grid); stroke-width:1; }}
  .axis {{ stroke:var(--axis); stroke-width:1; }}
  .tick {{ font-family:var(--mono); font-size:11px; fill:var(--ink-3); }}
  .ty {{ text-anchor:end; }} .tx {{ text-anchor:middle; }}
  .axis-title {{ font-family:var(--sans); font-size:12.5px; fill:var(--ink-2);
                 font-weight:500; }}
  .trend {{ stroke:var(--axis); stroke-width:1; }}
  .trend-label {{ font-family:var(--mono); font-size:10.5px; fill:var(--ink-3);
                  letter-spacing:.06em; }}
  .dot {{ fill:var(--series); stroke:var(--surface); stroke-width:2; }}
  .plabel {{ font-family:var(--sans); font-size:12.5px; fill:var(--ink-2);
             pointer-events:none; }}
  .hit {{ fill:transparent; cursor:pointer; outline:none; }}
  .hit:hover ~ .dot {{ }}
  .hit:focus-visible {{ stroke:var(--ink); stroke-width:2; }}

  .tip {{ position:fixed; z-index:20; pointer-events:none; opacity:0;
          transition:opacity .12s ease; background:var(--surface);
          border:1px solid var(--rule); border-radius:8px; padding:10px 12px;
          box-shadow:0 6px 22px rgba(0,0,0,.16); min-width:186px; }}
  @media (prefers-reduced-motion: reduce) {{ .tip {{ transition:none; }} }}
  .tip.on {{ opacity:1; }}
  .tip h4 {{ margin:0 0 2px; font-size:13.5px; font-weight:640; }}
  .tip .sub {{ font-family:var(--mono); font-size:11px; color:var(--ink-3);
               margin-bottom:7px; }}
  .tip dl {{ margin:0; display:grid; grid-template-columns:auto auto; gap:2px 14px; }}
  .tip dt {{ font-size:12px; color:var(--ink-2); }}
  .tip dd {{ margin:0; font-family:var(--mono); font-size:12px; text-align:right;
             font-variant-numeric:tabular-nums; }}

  h2 {{ margin:0 0 2px; font-size:15px; font-weight:620; letter-spacing:-.005em; }}
  .table-scroll {{ overflow-x:auto; }}
  table {{ border-collapse:collapse; width:100%; font-size:13px; }}
  caption {{ text-align:left; color:var(--ink-2); font-size:13px;
             padding-bottom:12px; }}
  th,td {{ padding:7px 10px; border-bottom:1px solid var(--rule);
           white-space:nowrap; }}
  thead th {{ font-family:var(--mono); font-size:10.5px; letter-spacing:.06em;
              text-transform:uppercase; color:var(--ink-3); font-weight:500;
              text-align:right; border-bottom-color:var(--axis); }}
  thead th:nth-child(-n+3) {{ text-align:left; }}
  tbody tr:last-child td {{ border-bottom:none; }}
  .rank {{ font-family:var(--mono); color:var(--ink-3); }}
  .nm {{ font-weight:530; }}
  td.n {{ font-family:var(--mono); text-align:right;
          font-variant-numeric:tabular-nums; }}

  .note {{ font-size:13px; color:var(--ink-2); max-width:70ch; }}
  .note strong {{ color:var(--ink); font-weight:600; }}
</style>

<div class="wrap">
  <header>
    <div class="eyebrow">2025 season · regular season · PPR</div>
    <h1>Scoring and efficiency mostly rise together</h1>
    <p class="lede">The twelve highest-scoring wide receivers of 2025, plotted by points
      per game against yards per route run. The two track each other closely
      (r&nbsp;=&nbsp;0.78), so the interesting players are the ones off the line:
      <strong>Ja'Marr Chase</strong> scored like a top-four receiver on the worst
      efficiency in the group, running the most routes of anyone here, while
      <strong>Zay Flowers</strong> and <strong>Jaxon Smith-Njigba</strong> beat the
      trend by the widest margins.</p>
  </header>

  <div class="card">
    <div class="chart-scroll">
{svg}
    </div>
  </div>

  <div class="card">
    <h2>All twelve, by the numbers</h2>
    <div class="table-scroll">
      <table>
        <caption>Ranked by total PPR points. Every plotted value appears here.</caption>
        <thead>
          <tr>
            <th>#</th><th>Player</th><th>Tm</th><th>G</th><th>PPR</th>
            <th>PPG</th><th>YPRR</th><th>Routes</th><th>Tgt</th><th>Rec yds</th>
          </tr>
        </thead>
        <tbody>
{rows}
        </tbody>
      </table>
    </div>
  </div>

  <p class="note"><strong>On the YPRR figure.</strong> Routes are estimated, not charted:
    <code>routes ≈ offensive snap share × team dropbacks</code>. That assumes a receiver
    runs a route on every dropback he's on the field for, so it overstates routes — and
    understates YPRR — for receivers who stay in to block. Use it to compare within a
    position group, not as a precise value. Charted routes are a paid PFF product.</p>
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
      '<div class="sub">' + d.team + ' · ' + d.games + ' games</div>' +
      '<dl>' +
        '<dt>Points/game</dt><dd>' + d.ppg.toFixed(2) + '</dd>' +
        '<dt>YPRR (est.)</dt><dd>' + d.yprr.toFixed(2) + '</dd>' +
        '<dt>Total PPR</dt><dd>' + d.total.toFixed(1) + '</dd>' +
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
    tip.style.left = x + 'px';
    tip.style.top = y + 'px';
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
    os.path.dirname(os.path.abspath(__file__)), "wr_chart_2025.html")
with open(out, "w") as f:
    f.write(html)
print("wrote", out)
