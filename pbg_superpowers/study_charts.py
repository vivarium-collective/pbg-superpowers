"""Static SVG helpers for study-finding visualizations.

These are STATIC, documentation-oriented SVGs designed to demonstrate a
study's findings — gate-test scoreboards, parameter-sweep heatmaps,
trajectory line charts — without requiring a live simulation.

They complement ``pbg_superpowers.visualization.Visualization`` (which
wires Composite-step viz that animate during a sim) by providing a
lightweight way to author per-study chart libraries that the dashboard
discovers automatically.

Convention
----------
Charts go in ``studies/<name>/charts/`` and the dashboard auto-discovers
them via vivarium-dashboard's ``_load_static_charts`` hook. Each SVG can
have a sidecar ``.meta.json`` with ``{title, caption}`` keys.

File ordering: prefix slugs with ``00_``, ``01_``, ... to control display
sequence in the Visualizations tab + downloadable HTML report.

Quick start
-----------

    from pbg_superpowers.study_charts import (
        finding_card_svg, bar_chart_svg, line_chart_svg, heatmap_svg,
        write_chart,
    )
    from pathlib import Path

    sd = Path("studies/my-study")

    # Gate-test scoreboard (one SVG card summarizing pass/fail per test).
    write_chart(sd, "00_summary", finding_card_svg(
        "my-study — gate-test scoreboard",
        [
            {"label": "Primary test A", "value": "707",  "badge": "pass"},
            {"label": "Primary test B", "value": "0.232", "badge": "pass"},
            {"label": "Supporting C",   "value": "115",  "badge": "fail"},
        ],
    ), title="My study scoreboard", caption="3 primary + 1 supporting test outcomes.")

    # Parameter-sweep bar chart with acceptance band.
    write_chart(sd, "01_param_sweep", bar_chart_svg(
        "DnaA count vs TE multiplier", x_labels=["1x","10x","20x","50x"],
        y_values=[115, 188, 296, 497], y_label="DnaA / cell",
        pass_band=(300, 800), pass_label="Schmidt 2016 [300, 800]",
    ), title="TE sweep — count", caption="Pass band shaded green.")

The signatures below return raw SVG strings so you can compose, post-process,
or write directly via ``write_chart``.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Iterable, Sequence


# ─── Color palette ──────────────────────────────────────────────────────

PALETTE = {
    "pass":      "#16a34a",
    "fail":      "#dc2626",
    "partial":   "#f59e0b",
    "info":      "#2563eb",
    "muted":     "#64748b",
    "ink":       "#0f172a",
    "stripe":    "#f8fafc",
    "border":    "#e5e7eb",
    "grid":      "#e5e7eb",
    "band_pass": "#86efac",
    "band_info": "#bfdbfe",
    "axis":      "#334155",
    "subtitle":  "#475569",
}

BADGE_LABELS = {
    "pass":    "✓ PASS",
    "fail":    "✗ FAIL",
    "partial": "⚠ PARTIAL",
    "info":    "◆ INFO",
}


# ─── SVG primitives ─────────────────────────────────────────────────────

def _svg_open(width: int, height: int, title: str = "") -> str:
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" '
        f'height="{height}" viewBox="0 0 {width} {height}" '
        f'font-family="-apple-system,sans-serif" font-size="13">'
        + (f'<title>{title}</title>' if title else '')
        + f'<rect width="{width}" height="{height}" fill="white"/>'
    )


def _svg_close() -> str:
    return '</svg>'


def _title_bar(width: int, title: str, subtitle: str = "") -> str:
    out = [
        f'<rect x="0" y="0" width="{width}" height="44" fill="{PALETTE["ink"]}"/>',
        f'<text x="{width/2}" y="28" text-anchor="middle" fill="white" '
        f'font-weight="600" font-size="15">{_esc(title)}</text>',
    ]
    if subtitle:
        out.append(
            f'<text x="{width/2}" y="60" text-anchor="middle" '
            f'fill="{PALETTE["muted"]}" font-size="11">{_esc(subtitle)}</text>'
        )
    return ''.join(out)


def _esc(s: str) -> str:
    if not isinstance(s, str):
        s = str(s)
    return (s.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;'))


# ─── Public chart generators ────────────────────────────────────────────

def finding_card_svg(
    title: str,
    rows: Sequence[dict],
    *,
    width: int = 760,
    row_height: int = 50,
    subtitle: str = "",
) -> str:
    """Render a 'finding scoreboard' card: title + a vertical stack of rows.

    Each row dict supports:
      label    str  — left-side label
      sublabel str  — optional grey sub-text under the label
      value    str  — right-side value (monospace)
      badge    str  — one of 'pass'|'fail'|'partial'|'info' (or None)
    """
    pad_left = 30
    pad_right = 30
    pad_top = 60 if subtitle else 60
    pad_bottom = 30
    plot_w = width - pad_left - pad_right
    height = pad_top + row_height * len(rows) + pad_bottom

    parts = [_svg_open(width, height, title)]
    parts.append(_title_bar(width, title, subtitle))

    row_y = pad_top
    for ln in rows:
        parts.append(
            f'<rect x="{pad_left}" y="{row_y}" width="{plot_w}" '
            f'height="{row_height - 6}" fill="{PALETTE["stripe"]}" rx="3"/>'
        )
        parts.append(
            f'<text x="{pad_left + 12}" y="{row_y + 20}" fill="{PALETTE["ink"]}" '
            f'font-weight="600">{_esc(ln.get("label", ""))}</text>'
        )
        if ln.get("sublabel"):
            parts.append(
                f'<text x="{pad_left + 12}" y="{row_y + 36}" '
                f'fill="{PALETTE["muted"]}" font-size="11">'
                f'{_esc(ln["sublabel"])}</text>'
            )
        if ln.get("value"):
            parts.append(
                f'<text x="{pad_left + plot_w - 160}" y="{row_y + 26}" '
                f'text-anchor="end" fill="{PALETTE["ink"]}" font-weight="600" '
                f'font-size="14" font-family="ui-monospace,monospace">'
                f'{_esc(ln["value"])}</text>'
            )
        b = ln.get("badge")
        if b and b in BADGE_LABELS:
            color = PALETTE.get(b, PALETTE["muted"])
            parts.append(
                f'<rect x="{pad_left + plot_w - 110}" y="{row_y + 10}" '
                f'width="100" height="24" rx="12" fill="{color}"/>'
            )
            parts.append(
                f'<text x="{pad_left + plot_w - 60}" y="{row_y + 26}" '
                f'text-anchor="middle" fill="white" font-weight="700" '
                f'font-size="11">{BADGE_LABELS[b]}</text>'
            )
        row_y += row_height

    parts.append(_svg_close())
    return '\n'.join(parts)


def bar_chart_svg(
    title: str,
    *,
    x_labels: Sequence[str],
    y_values: Sequence[float],
    y_label: str = "",
    subtitle: str = "",
    width: int = 760,
    height: int = 380,
    pass_band: tuple[float, float] | None = None,
    pass_label: str = "",
    bar_color: str = "#22c55e",
    value_format: str = ".0f",
) -> str:
    """Bar chart with optional shaded acceptance band.

    pass_band: (lower, upper) — if a bar's value is inside this band, it's
    drawn in bar_color; otherwise muted. Band is shaded green.
    """
    PL, PR, PT, PB = 60, 30, 60, 60
    plot_w = width - PL - PR
    plot_h = height - PT - PB

    if not y_values:
        return _svg_open(width, height) + _title_bar(width, title, subtitle) + _svg_close()

    y_max = max(y_values + ([pass_band[1]] if pass_band else [])) * 1.15
    if y_max <= 0:
        y_max = 1.0

    def x(i): return PL + (i + 0.5) * plot_w / len(y_values)
    def y(v): return PT + plot_h - (v / y_max) * plot_h

    bar_w = plot_w / max(len(y_values), 1) * 0.65

    parts = [_svg_open(width, height, title)]
    parts.append(_title_bar(width, title, subtitle))

    # Pass band shading
    if pass_band:
        lo, hi = pass_band
        parts.append(
            f'<rect x="{PL}" y="{y(hi)}" width="{plot_w}" '
            f'height="{y(lo)-y(hi)}" fill="{PALETTE["band_pass"]}" '
            f'fill-opacity="0.3"/>'
        )
        if pass_label:
            parts.append(
                f'<text x="{PL + plot_w - 8}" y="{y(hi) + 14}" '
                f'text-anchor="end" fill="{PALETTE["pass"]}" font-size="11">'
                f'{_esc(pass_label)}</text>'
            )

    # Y axis
    n_ticks = 5
    for i in range(n_ticks + 1):
        v = y_max * i / n_ticks
        yt = y(v)
        parts.append(
            f'<line x1="{PL}" y1="{yt}" x2="{PL+plot_w}" y2="{yt}" '
            f'stroke="{PALETTE["grid"]}"/>'
        )
        parts.append(
            f'<text x="{PL-8}" y="{yt+4}" text-anchor="end" '
            f'fill="{PALETTE["muted"]}">{v:.0f}</text>'
        )
    if y_label:
        parts.append(
            f'<text x="20" y="{PT+plot_h/2}" text-anchor="middle" '
            f'transform="rotate(-90 20 {PT+plot_h/2})" fill="{PALETTE["axis"]}">'
            f'{_esc(y_label)}</text>'
        )

    # Bars
    for i, v in enumerate(y_values):
        cx = x(i)
        bar_x = cx - bar_w / 2
        bt = y(v)
        in_band = pass_band is None or (pass_band[0] <= v <= pass_band[1])
        color = bar_color if in_band else PALETTE["muted"]
        parts.append(
            f'<rect x="{bar_x}" y="{bt}" width="{bar_w}" '
            f'height="{y(0)-bt}" fill="{color}"/>'
        )
        parts.append(
            f'<text x="{cx}" y="{bt-4}" text-anchor="middle" '
            f'fill="{PALETTE["ink"]}" font-size="11" font-weight="600">'
            f'{format(v, value_format)}</text>'
        )
        label = x_labels[i] if i < len(x_labels) else str(i)
        parts.append(
            f'<text x="{cx}" y="{PT+plot_h+18}" text-anchor="middle" '
            f'fill="{PALETTE["axis"]}">{_esc(label)}</text>'
        )

    parts.append(_svg_close())
    return '\n'.join(parts)


def line_chart_svg(
    title: str,
    *,
    series: Sequence[dict],
    x_label: str = "",
    y_label: str = "",
    subtitle: str = "",
    width: int = 900,
    height: int = 460,
    pass_band: tuple[float, float] | None = None,
    pass_label: str = "",
) -> str:
    """Multi-series line chart for trajectories.

    series: list of dicts {label, xs, ys, color, dashed?: bool}
    pass_band: optional (lower, upper) y-axis range shaded green.
    """
    PL, PR, PT, PB = 70, 30, 60, 70
    plot_w = width - PL - PR
    plot_h = height - PT - PB

    if not series:
        return _svg_open(width, height) + _title_bar(width, title, subtitle) + _svg_close()

    all_ys: list[float] = []
    all_xs: list[float] = []
    for s in series:
        all_xs.extend(s.get("xs", []))
        all_ys.extend(s.get("ys", []))
    if not all_xs or not all_ys:
        return _svg_open(width, height) + _title_bar(width, title, subtitle) + _svg_close()

    x_max = max(all_xs)
    y_max = max(all_ys) * 1.15
    y_min = min(all_ys + [0])
    if y_max <= y_min:
        y_max = y_min + 1.0

    def x(v): return PL + ((v - 0) / x_max) * plot_w
    def y(v): return PT + plot_h - ((v - y_min) / (y_max - y_min)) * plot_h

    parts = [_svg_open(width, height, title)]
    parts.append(_title_bar(width, title, subtitle))

    # Pass band
    if pass_band:
        lo, hi = pass_band
        parts.append(
            f'<rect x="{PL}" y="{y(hi)}" width="{plot_w}" '
            f'height="{y(lo)-y(hi)}" fill="{PALETTE["band_pass"]}" '
            f'fill-opacity="0.3"/>'
        )
        if pass_label:
            parts.append(
                f'<text x="{PL + 10}" y="{y(hi) + 14}" fill="{PALETTE["pass"]}" '
                f'font-size="11">{_esc(pass_label)}</text>'
            )

    # Y ticks
    n_ticks = 5
    for i in range(n_ticks + 1):
        v = y_min + (y_max - y_min) * i / n_ticks
        yt = y(v)
        parts.append(
            f'<line x1="{PL}" y1="{yt}" x2="{PL+plot_w}" y2="{yt}" '
            f'stroke="{PALETTE["grid"]}"/>'
        )
        parts.append(
            f'<text x="{PL-8}" y="{yt+4}" text-anchor="end" '
            f'fill="{PALETTE["muted"]}">{v:.0f}</text>'
        )
    # X ticks
    for i in range(6):
        tv = x_max * i / 5
        xt = x(tv)
        parts.append(
            f'<text x="{xt}" y="{PT+plot_h+18}" text-anchor="middle" '
            f'fill="{PALETTE["muted"]}">{tv:.0f}</text>'
        )

    if y_label:
        parts.append(
            f'<text x="20" y="{PT+plot_h/2}" text-anchor="middle" '
            f'transform="rotate(-90 20 {PT+plot_h/2})" fill="{PALETTE["axis"]}">'
            f'{_esc(y_label)}</text>'
        )
    if x_label:
        parts.append(
            f'<text x="{(PL+PL+plot_w)/2}" y="{PT+plot_h+44}" '
            f'text-anchor="middle" fill="{PALETTE["axis"]}">{_esc(x_label)}</text>'
        )

    # Series paths
    for s in series:
        xs = s.get("xs", []); ys = s.get("ys", [])
        if not xs or not ys: continue
        path = 'M ' + ' L '.join(f'{x(xv):.1f},{y(yv):.1f}' for xv, yv in zip(xs, ys))
        color = s.get("color", "#2563eb")
        sw = s.get("stroke_width", 2)
        da = ' stroke-dasharray="4,3"' if s.get("dashed") else ''
        parts.append(
            f'<path d="{path}" fill="none" stroke="{color}" '
            f'stroke-width="{sw}"{da}/>'
        )

    # Legend
    ly = 55
    for s in series:
        color = s.get("color", "#2563eb")
        parts.append(f'<rect x="{PL}" y="{ly-9}" width="14" height="14" fill="{color}"/>')
        parts.append(f'<text x="{PL+22}" y="{ly+3}" fill="{PALETTE["axis"]}">{_esc(s.get("label", ""))}</text>')
        ly += 16

    parts.append(_svg_close())
    return '\n'.join(parts)


def heatmap_svg(
    title: str,
    *,
    row_labels: Sequence[str],
    col_labels: Sequence[str],
    values: Sequence[Sequence[float]],
    subtitle: str = "",
    width: int = 760,
    cmap_low: str = "#cbd5e1",
    cmap_high: str = "#16a34a",
    vmin: float | None = None,
    vmax: float | None = None,
    value_format: str = ".0f",
) -> str:
    """Heatmap: rows × cols grid, cells colored by value."""
    if not values or not row_labels or not col_labels:
        return _svg_open(width, 60) + _title_bar(width, title, subtitle) + _svg_close()

    flat = [v for row in values for v in row if v is not None]
    if vmin is None: vmin = min(flat) if flat else 0
    if vmax is None: vmax = max(flat) if flat else 1
    if vmax <= vmin: vmax = vmin + 1.0

    PL, PT = 80, 60
    cell_w = (width - PL - 30) / max(len(col_labels), 1)
    cell_h = 55
    height = PT + cell_h * len(row_labels) + 40

    def hex2rgb(h):
        return tuple(int(h[i:i+2], 16) for i in (1, 3, 5))

    def color_for(v):
        if v is None: return PALETTE["stripe"]
        t = max(0.0, min(1.0, (v - vmin) / (vmax - vmin)))
        lo, hi = hex2rgb(cmap_low), hex2rgb(cmap_high)
        rgb = [int(lo[i] + (hi[i] - lo[i]) * t) for i in range(3)]
        return '#' + ''.join(f'{x:02x}' for x in rgb)

    parts = [_svg_open(width, height, title)]
    parts.append(_title_bar(width, title, subtitle))

    # Header row (cols)
    for j, col in enumerate(col_labels):
        cx = PL + j * cell_w + cell_w / 2
        parts.append(
            f'<text x="{cx}" y="{PT - 12}" text-anchor="middle" '
            f'fill="{PALETTE["axis"]}" font-weight="600">{_esc(col)}</text>'
        )

    # Cells + row labels
    for i, row_label in enumerate(row_labels):
        cy = PT + i * cell_h + cell_h / 2
        parts.append(
            f'<text x="{PL - 10}" y="{cy + 4}" text-anchor="end" '
            f'fill="{PALETTE["axis"]}" font-weight="600">{_esc(row_label)}</text>'
        )
        for j, _ in enumerate(col_labels):
            v = values[i][j] if i < len(values) and j < len(values[i]) else None
            x = PL + j * cell_w
            y = PT + i * cell_h
            fill = color_for(v)
            parts.append(
                f'<rect x="{x}" y="{y}" width="{cell_w-3}" '
                f'height="{cell_h-3}" fill="{fill}" stroke="#94a3b8"/>'
            )
            label = format(v, value_format) if v is not None else '—'
            t = (v - vmin) / (vmax - vmin) if v is not None and vmax > vmin else 0.5
            text_color = "#fff" if abs(t - 0.5) > 0.35 else PALETTE["ink"]
            parts.append(
                f'<text x="{x + cell_w/2}" y="{y + cell_h/2 + 4}" '
                f'text-anchor="middle" fill="{text_color}" font-weight="600">'
                f'{label}</text>'
            )

    parts.append(_svg_close())
    return '\n'.join(parts)


# ─── Persistence ────────────────────────────────────────────────────────

def write_chart(
    study_dir: str | Path,
    slug: str,
    svg: str,
    *,
    title: str = "",
    caption: str = "",
) -> Path:
    """Write SVG + sidecar .meta.json to <study_dir>/charts/<slug>.svg.

    Returns the SVG path. Creates the charts/ directory if needed.

    The dashboard's vivarium_dashboard.lib.study_charts._load_static_charts
    auto-discovers these files, so they appear in the Visualizations tab
    of the dashboard AND in the downloadable investigation HTML report
    with no further wiring.
    """
    study_dir = Path(study_dir)
    charts_dir = study_dir / "charts"
    charts_dir.mkdir(exist_ok=True)
    svg_path = charts_dir / f"{slug}.svg"
    svg_path.write_text(svg)
    meta_path = charts_dir / f"{slug}.meta.json"
    meta_path.write_text(json.dumps({"title": title, "caption": caption}, indent=2))
    return svg_path


def chromosome_circle_svg(
    title: str,
    *,
    panels: Sequence[dict],
    genome_len: int,
    subtitle: str = "",
    width: int = 1400,
    panel_radius: int = 130,
    panel_spacing: int = 60,
) -> str:
    """Render circular chromosome diagram(s) with feature markers.

    Pattern used in genome biology to show feature positions (oriC, ter,
    RNAP, replisomes, DnaA boxes, regulatory regions...) at their actual
    genomic coordinates. Multiple panels show different timepoints or
    conditions side-by-side; each panel can itself contain multiple
    chromosomes (for post-replication 2-chromosome states).

    Each panel dict:
        label: str                 — title above the panel
        chromosomes: list[dict]    — one or more circles, each with:
            features: dict[str, list[dict]]
                where each feature dict has:
                  coord:    int     — genomic position in bp (signed; 0 = oriC)
                  marker:   str     — 'circle' | 'square' | 'triangle_up'
                  color:    str     — hex color
                  size:     int     — marker radius in px
                  category: str     — used to deduplicate legend entries

    Example:
        chromosome_circle_svg(
            "DnaA-box landscape", panels=[{
                "label": "t=0",
                "chromosomes": [{
                    "features": {
                        "oriC":    [{"coord": 0, "marker": "circle",  "color": "#16a34a", "size": 8, "category": "OriC"}],
                        "ter":     [{"coord": 2_320_000, "marker": "square", "color": "#dc2626", "size": 7, "category": "Ter"}],
                        "boxes":   [{"coord": c, "marker": "circle", "color": "#94a3b8", "size": 2, "category": "DnaA-box"} for c in box_coords],
                        "replisomes": [{"coord": 1_331_293, "marker": "triangle_up", "color": "#f59e0b", "size": 7, "category": "Replisome"}],
                    },
                }],
            }],
            genome_len=4_641_652,
        )
    """
    import math

    PT = 60 if subtitle else 50
    PB = 80

    # Layout: distribute panels horizontally. Each panel may stack chromosomes vertically.
    n_panels = len(panels)
    if n_panels == 0:
        return _svg_open(width, 80, title) + _title_bar(width, title, subtitle) + _svg_close()

    # Compute panel widths so they fit
    cell_w = (width - panel_spacing * (n_panels + 1)) / n_panels
    if cell_w < panel_radius * 2 + 20:
        # Auto-shrink radius to fit
        panel_radius = max(60, int((cell_w - 20) / 2))

    # Compute total height based on max chromosomes per panel
    max_chr = max(len(p.get("chromosomes", [{}])) for p in panels)
    chr_spacing = 20
    chr_unit_h = panel_radius * 2 + chr_spacing + 30  # circle + label + gap
    panel_total_h = chr_unit_h * max_chr + 40
    height = PT + panel_total_h + PB

    parts = [_svg_open(width, height, title)]
    parts.append(_title_bar(width, title, subtitle))

    # Track unique legend entries
    legend_entries: dict[str, dict] = {}  # category -> {marker, color, size}

    def marker_path(cx, cy, mk, size, color, angle=0.0):
        if mk == 'circle':
            return f'<circle cx="{cx}" cy="{cy}" r="{size}" fill="{color}"/>'
        elif mk == 'square':
            return f'<rect x="{cx-size}" y="{cy-size}" width="{size*2}" height="{size*2}" fill="{color}"/>'
        elif mk == 'triangle_up':
            return (f'<polygon points="{cx},{cy-size} '
                    f'{cx-size},{cy+size*0.7} {cx+size},{cy+size*0.7}" fill="{color}"/>')
        elif mk == 'tick':
            # Radial tick — line points outward along the radius at the given angle.
            # The radial unit vector at angle θ (0 = top, clockwise) is (sin θ, -cos θ).
            # We draw a tick straddling the placement point, half inside and half outside.
            dx = math.sin(angle) * size
            dy = -math.cos(angle) * size
            return (f'<line x1="{cx-dx}" y1="{cy-dy}" x2="{cx+dx}" y2="{cy+dy}" '
                    f'stroke="{color}" stroke-width="1.2"/>')
        return f'<circle cx="{cx}" cy="{cy}" r="{size}" fill="{color}"/>'

    for pi, panel in enumerate(panels):
        panel_cx = panel_spacing + cell_w * (pi + 0.5) + panel_spacing * pi - panel_spacing * pi
        panel_cx = panel_spacing + cell_w / 2 + (cell_w + panel_spacing) * pi

        chromosomes = panel.get("chromosomes", [])
        # Panel label
        parts.append(
            f'<text x="{panel_cx}" y="{PT + 10}" text-anchor="middle" '
            f'fill="{PALETTE["ink"]}" font-weight="600" font-size="13">'
            f'{_esc(panel.get("label", ""))}</text>'
        )

        for ci, chrom in enumerate(chromosomes):
            cy_center = PT + 30 + chr_unit_h * ci + panel_radius
            # Backbone
            parts.append(
                f'<circle cx="{panel_cx}" cy="{cy_center}" r="{panel_radius}" '
                f'fill="none" stroke="#cbd5e1" stroke-width="2"/>'
            )

            features = chrom.get("features", {})
            # Render in stable order; small markers first so big ones overlay
            order_by_size = []
            for cat_key, items in features.items():
                for item in items:
                    order_by_size.append((item.get("size", 3), cat_key, item))
            order_by_size.sort(key=lambda t: t[0])
            for _, cat_key, item in order_by_size:
                coord = item.get("coord", 0)
                angle = (coord / genome_len) * 2 * math.pi  # 0 = top (oriC)
                # Marker placement: small markers slightly INSIDE ring, big markers ON ring
                size = item.get("size", 3)
                offset = 0 if size > 4 else -size  # tiny markers inset, large markers on backbone
                r = panel_radius + offset if item.get("outside") else panel_radius
                cx = panel_cx + r * math.sin(angle)
                cy = cy_center - r * math.cos(angle)
                color = item.get("color", "#64748b")
                marker = item.get("marker", "circle")
                parts.append(marker_path(cx, cy, marker, size, color, angle))
                # Legend dedup
                cat_name = item.get("category", cat_key)
                if cat_name not in legend_entries:
                    legend_entries[cat_name] = {
                        "marker": marker, "color": color, "size": min(size, 6),
                    }

    # Legend at bottom
    ly = height - 30
    parts.append(
        f'<text x="{panel_spacing}" y="{ly}" fill="{PALETTE["axis"]}" '
        f'font-weight="600">Legend:</text>'
    )
    lx = panel_spacing + 80
    for cat, meta in legend_entries.items():
        parts.append(marker_path(lx + 6, ly - 4, meta["marker"], meta["size"], meta["color"]))
        parts.append(
            f'<text x="{lx + 18}" y="{ly}" fill="{PALETTE["axis"]}">{_esc(cat)}</text>'
        )
        lx += 8 + 18 + 8 + 9 * len(cat)

    parts.append(_svg_close())
    return '\n'.join(parts)


def copy_chart(
    study_dir: str | Path,
    slug: str,
    src_svg_path: str | Path,
    *,
    title: str = "",
    caption: str = "",
) -> Path:
    """Copy an existing SVG into <study_dir>/charts/<slug>.svg + sidecar.

    Useful when a probe script writes one canonical SVG and multiple
    studies want to reference it.
    """
    import shutil
    study_dir = Path(study_dir)
    src = Path(src_svg_path)
    charts_dir = study_dir / "charts"
    charts_dir.mkdir(exist_ok=True)
    dst = charts_dir / f"{slug}.svg"
    shutil.copy(src, dst)
    (charts_dir / f"{slug}.meta.json").write_text(
        json.dumps({"title": title, "caption": caption}, indent=2)
    )
    return dst
