"""Emit a panel wiring diagram (SVG) from board geometry + the harness.

pcbnew's plotters draw layers, not nets — so a plotted board always looks like
a PCB. This emitter draws what an electrician expects instead: device outlines
with labeled terminals, wires as thick lines in their actual insulation color,
a wire-number flag on every run, and a title block. Everything is stdlib —
this output must work in KiCad's bare Python, like the CSV.

Input is the neutral `BoardGeometry` (from KicadBoardSource.load_geometry())
plus the resolved `Harness` (for wire colors and numbers), so the emitter has
no KiCad knowledge and can later be fed from any physical view.
"""
from __future__ import annotations
from ..model import BoardGeometry, Harness

# IEC 60757 color codes -> display hex. GNYE is handled specially (striped).
COLOR_HEX = {
    "BK": "#1A1A1A", "BN": "#7B3F00", "RD": "#C81E1E", "OG": "#F07800",
    "YE": "#E0C000", "GN": "#0E9F2E", "BU": "#0055C8", "VT": "#7D2AC8",
    "GY": "#8A8A8A", "WH": "#E8E8E8", "PK": "#F0A0BE", "TQ": "#30D5C8",
    "SR": "#C0C0C0", "GD": "#D4AF37",
}
_FALLBACK = "#606060"          # wires with no color: neutral gray


def _wire_color(spec_color: str) -> tuple:
    """-> (hex, striped_hex_or_None). Accepts IEC codes or '#RRGGBB'."""
    c = (spec_color or "").strip()
    if c.upper() == "GNYE":
        return COLOR_HEX["GN"], COLOR_HEX["YE"]
    if c.startswith("#") and len(c) >= 7:
        return c[:7], None
    return COLOR_HEX.get(c.upper(), _FALLBACK), None


def _esc(s) -> str:
    return (str(s).replace("&", "&amp;").replace("<", "&lt;")
            .replace(">", "&gt;").replace('"', "&quot;"))


def _pts(polyline) -> str:
    return " ".join(f"{x:.2f},{y:.2f}" for x, y in polyline)


def build_panel_svg(harness: Harness, geometry: BoardGeometry) -> str:
    # wire metadata by net
    color_by_net: dict = {}
    label_by_net: dict = {}
    for w in harness.wires:
        color_by_net.setdefault(w.net, w.spec.color)
        label_by_net.setdefault(w.net, w.spec.wire_no)

    # bounds: board edge if drawn, else everything else
    xs, ys = [], []
    for pl in geometry.edges:
        for x, y in pl:
            xs.append(x); ys.append(y)
    if not xs:
        for fg in geometry.footprints.values():
            for pl in fg.outlines:
                for x, y in pl:
                    xs.append(x); ys.append(y)
            for (x, y, _d) in fg.pads.values():
                xs.append(x); ys.append(y)
        for _n, (x1, y1), (x2, y2), _w in geometry.tracks:
            xs.extend((x1, x2)); ys.extend((y1, y2))
    if not xs:
        xs, ys = [0, 100], [0, 100]
    m = 8.0
    x0, y0 = min(xs) - m, min(ys) - m
    bw, bh = (max(xs) - min(xs)) + 2 * m, (max(ys) - min(ys)) + 2 * m

    out = []
    out.append(f'<svg xmlns="http://www.w3.org/2000/svg" '
               f'viewBox="{x0:.2f} {y0:.2f} {bw:.2f} {bh:.2f}" '
               f'width="{bw * 4:.0f}" height="{bh * 4:.0f}" '
               f'font-family="sans-serif">')
    out.append(f'<rect x="{x0:.2f}" y="{y0:.2f}" width="{bw:.2f}" '
               f'height="{bh:.2f}" fill="#FFFFFF"/>')

    # panel edge
    for pl in geometry.edges:
        out.append(f'<polyline points="{_pts(pl)}" fill="none" '
                   f'stroke="#202020" stroke-width="0.5"/>')

    # wires under devices' labels but above nothing else: draw first the runs
    flags = []
    for net, (ax, ay), (bx, by), w in geometry.tracks:
        hexc, stripe = _wire_color(color_by_net.get(net, ""))
        sw = max(w, 0.8)
        out.append(f'<line x1="{ax:.2f}" y1="{ay:.2f}" x2="{bx:.2f}" '
                   f'y2="{by:.2f}" stroke="{hexc}" stroke-width="{sw:.2f}" '
                   f'stroke-linecap="round"/>')
        if stripe:
            out.append(f'<line x1="{ax:.2f}" y1="{ay:.2f}" x2="{bx:.2f}" '
                       f'y2="{by:.2f}" stroke="{stripe}" '
                       f'stroke-width="{sw * 0.45:.2f}" stroke-linecap="round" '
                       f'stroke-dasharray="{sw * 1.6:.2f},{sw * 1.6:.2f}"/>')

    # one wire-number flag per net, on its longest segment; parallel runs in a
    # bundle share midpoints, so nudge each new flag until it clears the rest
    best: dict = {}
    for net, (ax, ay), (bx, by), _w in geometry.tracks:
        ln = (bx - ax) ** 2 + (by - ay) ** 2
        if ln > best.get(net, (0, None, None))[0]:
            best[net] = (ln, ((ax + bx) / 2, (ay + by) / 2), (ax, ay, bx, by))
    placed: list = []
    for net in sorted(best):
        label = label_by_net.get(net, "")
        if not label:
            continue
        _ln, (cx, cy), _seg = best[net]
        while any((cx - px) ** 2 + (cy - py) ** 2 < 6.0 ** 2
                  for px, py in placed):
            cy -= 3.4
        placed.append((cx, cy))
        flags.append(
            f'<text x="{cx:.2f}" y="{cy - 1.2:.2f}" font-size="2.6" '
            f'text-anchor="middle" fill="#101010" stroke="#FFFFFF" '
            f'stroke-width="0.7" paint-order="stroke">{_esc(label)}</text>')

    # devices
    for fg in geometry.footprints.values():
        for pl in fg.outlines:
            out.append(f'<polyline points="{_pts(pl)}" fill="none" '
                       f'stroke="#303030" stroke-width="0.35"/>')
        for pin, (px, py, dia) in fg.pads.items():
            r = max(dia / 2, 0.7)
            out.append(f'<circle cx="{px:.2f}" cy="{py:.2f}" r="{r:.2f}" '
                       f'fill="#FFFFFF" stroke="#404040" stroke-width="0.25"/>')
            out.append(f'<text x="{px:.2f}" y="{py + r + 2.2:.2f}" '
                       f'font-size="1.8" text-anchor="middle" '
                       f'fill="#333333">{_esc(pin)}</text>')
        out.append(f'<text x="{fg.x:.2f}" y="{fg.y:.2f}" font-size="3.2" '
                   f'font-weight="bold" text-anchor="middle" fill="#000000" '
                   f'stroke="#FFFFFF" stroke-width="0.8" '
                   f'paint-order="stroke">{_esc(fg.ref)}</text>')

    out.extend(flags)                      # flags on top of everything

    # title block, bottom-right inside the frame
    t = geometry.title or {}
    if any(t.values()):
        tx, ty = x0 + bw - 2.5, y0 + bh - 2.5
        line = " — ".join(v for v in (t.get("title"), t.get("company"),
                                      f"rev {t['rev']}" if t.get("rev") else "",
                                      t.get("date")) if v)
        out.append(f'<text x="{tx:.2f}" y="{ty:.2f}" font-size="3.0" '
                   f'text-anchor="end" fill="#202020">{_esc(line)}</text>')

    out.append("</svg>")
    return "\n".join(out)


def write_panel_svg(harness: Harness, geometry: BoardGeometry, path: str) -> None:
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(build_panel_svg(harness, geometry))
        fh.write("\n")
