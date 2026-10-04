"""
One-page PDF summary of a building's screening results.
"""
from berdo.regulations import (
    ACP_RATE,
    BERDO_LINKS,
    PATHWAYS_VERIFIED,
)


def build_building_summary_pdf(s: dict) -> bytes:
    """
    One-page PDF of a building's screening results and options, for sharing with a
    board, lender, or consultant. Every figure is labeled Reported, Calculated, or
    Estimated. KeepInFrame(shrink) guarantees the content fits on one page.

    s keys: address, owner, data_year, facts [(item, value, source)],
    periods [dict], limit_basis, blend_note, grid_note, notes [str], pathways [dict].
    """
    from io import BytesIO
    from xml.sax.saxutils import escape
    import datetime as _dt
    from reportlab.lib.pagesizes import letter
    from reportlab.lib import colors
    from reportlab.lib.units import inch
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.platypus import (SimpleDocTemplate, Paragraph, Spacer, Table,
                                    TableStyle, KeepInFrame)

    def esc(x):
        return escape(str(x)) if x is not None else ""

    def co2(text):
        #Built-in PDF fonts have no subscript-2 glyph, so use markup instead
        return text.replace("CO₂", "CO<sub>2</sub>").replace("CO2e", "CO<sub>2</sub>e")

    base = getSampleStyleSheet()
    ink, muted, accent, rule = (colors.HexColor("#1F2A37"), colors.HexColor("#5B6573"),
                                colors.HexColor("#2F5D8A"), colors.HexColor("#D5DAE1"))
    st_title = ParagraphStyle("t", parent=base["Title"], fontName="Helvetica-Bold",
                              fontSize=15, leading=18, alignment=0, spaceAfter=2, textColor=ink)
    st_sub   = ParagraphStyle("s", parent=base["Normal"], fontName="Helvetica-Bold",
                              fontSize=11, leading=14, textColor=ink)
    st_meta  = ParagraphStyle("m", parent=base["Normal"], fontSize=8, leading=10, textColor=muted)
    st_h     = ParagraphStyle("h", parent=base["Normal"], fontName="Helvetica-Bold",
                              fontSize=9.5, leading=12, textColor=accent, spaceBefore=7, spaceAfter=3)
    st_body  = ParagraphStyle("b", parent=base["Normal"], fontSize=8, leading=10, textColor=ink)
    st_cell  = ParagraphStyle("c", parent=st_body, fontSize=7.8, leading=9.5)
    st_cellb = ParagraphStyle("cb", parent=st_cell, fontName="Helvetica-Bold")
    st_small = ParagraphStyle("sm", parent=st_body, fontSize=7, leading=8.6, textColor=muted)

    def P(text, style=st_cell):
        return Paragraph(text, style)

    grid = TableStyle([
        ("LINEBELOW", (0, 0), (-1, 0), 0.8, accent),
        ("LINEBELOW", (0, 1), (-1, -1), 0.3, rule),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING", (0, 0), (-1, -1), 2), ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
        ("LEFTPADDING", (0, 0), (-1, -1), 3), ("RIGHTPADDING", (0, 0), (-1, -1), 3),
    ])

    story = []
    today = _dt.date.today()
    story.append(P("BERDO Screening Summary", st_title))
    story.append(P(esc(s.get("address", "")), st_sub))
    story.append(P(
        f"Owner: {esc(s.get('owner') or 'Not reported')} &nbsp;·&nbsp; "
        f"Data year: {esc(s.get('data_year') or 'Not specified')} &nbsp;·&nbsp; "
        f"Generated {today.strftime('%B')} {today.day}, {today.year}", st_meta))
    story.append(Spacer(1, 5))

    banner = Table([[P(
        "<b>Screening estimate, not an official City of Boston compliance determination.</b> "
        "Figures are labeled <b>Reported</b> (from the City's public BERDO data), "
        "<b>Calculated</b> (by this tool from reported data), or <b>Estimated</b> "
        "(depends on this tool's assumptions).", st_body)]], colWidths=[7.3 * inch], hAlign="LEFT")
    banner.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#EEF3F8")),
        ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#B8C7D9")),
        ("LEFTPADDING", (0, 0), (-1, -1), 6), ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 4), ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    story.append(banner)

    #Building at a glance: two side-by-side fact tables
    story.append(P("Building at a glance", st_h))
    facts = s.get("facts", [])
    half = (len(facts) + 1) // 2
    #One table with two halves (Item | Value | Source, gap, Item | Value | Source), so
    #each row has a single height and every rule lines up across the page.
    left, right = facts[:half], facts[half:]
    right += [("", "", "")] * (len(left) - len(right))
    hdr = [P("<b>Item</b>"), P("<b>Value</b>"), P("<b>Source</b>")]
    data = [hdr + [""] + hdr]
    for (a1, b1, c1), (a2, b2, c2) in zip(left, right):
        data.append([P(esc(a1)), P(co2(esc(b1))), P(esc(c1), st_small), "",
                     P(esc(a2)), P(co2(esc(b2))), P(esc(c2), st_small)])
    gap = 0.2
    half_w = (7.3 - gap) / 2                       #3.55 in per half; total 7.3 in
    col_w = [1.25, 1.45, half_w - 2.7]
    facts_t = Table(data, colWidths=[w * inch for w in col_w + [gap] + col_w], hAlign="LEFT")
    facts_t.setStyle(TableStyle([
        #Rules drawn per half so they don't cross the gap column
        ("LINEBELOW", (0, 0), (2, 0), 0.8, accent),
        ("LINEBELOW", (4, 0), (6, 0), 0.8, accent),
        ("LINEBELOW", (0, 1), (2, -1), 0.3, rule),
        ("LINEBELOW", (4, 1), (6, -1), 0.3, rule),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING", (0, 0), (-1, -1), 2), ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
        ("LEFTPADDING", (0, 0), (-1, -1), 3), ("RIGHTPADDING", (0, 0), (-1, -1), 3),
        ("LEFTPADDING", (3, 0), (3, -1), 0), ("RIGHTPADDING", (3, 0), (3, -1), 0),
    ]))
    story.append(facts_t)

    #Emissions limit by period
    periods = s.get("periods", [])
    if periods:
        story.append(P("Emissions limit by compliance period", st_h))
        has_grid = any(p.get("grid_status") for p in periods)
        head = ["Period", "Limit (kg CO2e/sf/yr)", "Gap vs. current intensity",
                "Status at current emissions", "Est. annual ACP"]
        if has_grid:
            head.append("Grid scenario")
        data = [[P(f"<b>{co2(h)}</b>") for h in head]]
        for p in periods:
            row = [P(esc(p["period"])), P(f"{p['limit']:.2f}"),
                   P(f"{p['gap']:+.2f}"),
                   P(esc(p["status"]), st_cellb if p["status"] == "Over limit" else st_cell),
                   P(f"USD {p['acp']:,.0f}" if p["acp"] else "USD 0")]
            if has_grid:
                row.append(P(esc(p.get("grid_status") or "")))
            data.append(row)
        widths = [0.8, 1.35, 1.35, 1.6, 1.1] + ([1.1] if has_grid else [])
        scale = 7.3 / sum(widths)   #always span the full page width, with or without the grid column
        t = Table(data, colWidths=[w * scale * inch for w in widths], hAlign="LEFT")
        t.setStyle(grid)
        story.append(t)
        cap = [esc(s.get("limit_basis", ""))]
        if s.get("blend_note"):
            cap.append(esc(s["blend_note"]))
        if s.get("grid_note"):
            cap.append(esc(s["grid_note"]))
        cap.append("Limits: Reported (BERDO emissions standards). Gap and status: Calculated. "
                   f"ACP: Estimated at USD {ACP_RATE} per metric ton over the limit, "
                   "assuming emissions stay flat. The 2050+ row is an annual figure with no end date.")
        story.append(Spacer(1, 2))
        story.append(P(co2(" ".join(c for c in cap if c)), st_small))

    #Screening notes
    notes = [n for n in s.get("notes", []) if n]
    if notes:
        story.append(P("Screening notes", st_h))
        for n in notes[:6]:
            story.append(P(f"• {co2(esc(n))}", st_body))

    #Options
    pw = s.get("pathways", [])
    if pw:
        story.append(P("Options to consider", st_h))
        ordered = sorted(pw, key=lambda p: not p["strong"])
        data = [[P("<b>Option</b>"), P("<b>For this building</b>"),
                 P("<b>Approval · Deadline</b>"), P("<b>Official link</b>")]]
        for p in ordered:
            label, url = p["links"][0]
            data.append([
                P(("<b>" if p["strong"] else "") + esc(p["name"]) + ("</b>" if p["strong"] else "")),
                P(co2(esc(p["why"][:1].upper() + p["why"][1:]))),
                P(f"{esc(p['approval'])} · {esc(p['deadline'])}", st_small),
                P(f'<link href="{esc(url)}" color="#2F5D8A"><u>{esc(label)}</u></link>', st_small),
            ])
        t = Table(data, colWidths=[1.45 * inch, 2.75 * inch, 1.75 * inch, 1.35 * inch], hAlign="LEFT")
        t.setStyle(grid)
        story.append(t)
        story.append(Spacer(1, 2))
        story.append(P("Options in bold are most relevant to this building's screening result. "
                       "Listing an option is not a determination of eligibility.", st_small))

    #Footer
    story.append(Spacer(1, 6))
    story.append(P(
        "Sources: City of Boston BERDO public data disclosure; BERDO emissions standards; "
        f"boston.gov BERDO and Review Board pages (pathways and deadlines verified {PATHWAYS_VERIFIED}). "
        f'Questions about official compliance: <link href="{BERDO_LINKS["one_on_one"]}" color="#2F5D8A">'
        "<u>schedule a call with BERDO staff</u></link>. "
        "Prepared with the BERDO Priority Screening Tool. Not financial, legal, or tax advice.",
        st_small))

    buf = BytesIO()
    margin = 0.5 * inch
    doc = SimpleDocTemplate(buf, pagesize=letter, leftMargin=margin, rightMargin=margin,
                            topMargin=margin, bottomMargin=margin,
                            title=f"BERDO Screening Summary: {s.get('address', '')}",
                            author="BERDO Priority Screening Tool")
    frame_w, frame_h = letter[0] - 2 * margin, letter[1] - 2 * margin
    doc.build([KeepInFrame(frame_w, frame_h - 2, story, mode="shrink")])
    return buf.getvalue()
