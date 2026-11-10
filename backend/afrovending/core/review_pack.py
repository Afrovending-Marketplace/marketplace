"""Builds the Marketplace Legal Policy Review Pack (.docx and .pdf) from the current policy versions in the database."""
import re
from datetime import datetime
from pathlib import Path

from markdown_it import MarkdownIt

from afrovending.core import policies as pol
from afrovending.core import review_pack_content as C

TITLE1 = "AFROVENDING ONLINE MARKETPLACE LLC"
TITLE2 = "MARKETPLACE LEGAL POLICY REVIEW PACK"
CONF = "Confidential — Draft for Attorney Review"
NOT_APPROVED = "NOT LEGALLY APPROVED — These drafts have not been reviewed or approved by legal counsel and must not be published or relied on."
STATUS_LABEL = {"draft": "Draft", "pending_review": "Draft — Pending Legal Review", "approved": "Approved", "published": "Published", "archived": "Archived"}
INLINE = re.compile(r"(\*\*.+?\*\*|`[^`]+`|\[[^\]\s][^\]]*\])")


def md_blocks(md: str) -> list[tuple]:
    """Markdown → simple blocks: ("h", level, text) ("p", text) ("li", text, depth, marker) ("table", rows) ("callout", text)."""
    toks = MarkdownIt("commonmark").enable("table").parse(md)
    out, lists, quote, table, row = [], [], False, None, None
    for i, t in enumerate(toks):
        if t.type == "heading_open":
            level = int(t.tag[1])
            if level > 1:
                out.append(("h", level, toks[i + 1].content))
        elif t.type in ("bullet_list_open", "ordered_list_open"):
            lists.append([t.type == "ordered_list_open", int(t.attrs.get("start", 1) or 1) - 1, True])
        elif t.type in ("bullet_list_close", "ordered_list_close"):
            lists.pop()
        elif t.type == "list_item_open":
            lists[-1][1] += 1
            lists[-1][2] = True
        elif t.type == "blockquote_open":
            quote = True
        elif t.type == "blockquote_close":
            quote = False
        elif t.type == "table_open":
            table = []
        elif t.type == "tr_open":
            row = []
        elif t.type in ("th_open", "td_open"):
            row.append(toks[i + 1].content)
        elif t.type == "tr_close":
            table.append(row)
        elif t.type == "table_close":
            out.append(("table", table))
            table = None
        elif t.type == "paragraph_open" and table is None:
            text = toks[i + 1].content.replace("\n", " ")
            if quote:
                out.append(("callout", text))
            elif lists:
                ordered, n, first = lists[-1]
                marker = (f"{n}." if ordered else "•") if first else ""
                lists[-1][2] = False
                out.append(("li", text, len(lists), marker))
            else:
                out.append(("p", text))
    return out


def _date(v) -> str:
    return v.strftime("%B %d, %Y") if isinstance(v, datetime) else (v or "—")


async def gather() -> dict:
    from afrovending.core.db import db
    rows = []
    for slug, m in pol.META.items():
        v = await db.policy_versions.find_one({"slug": slug, "status": {"$in": ["pending_review", "draft", "approved"]}}, sort=[("version", -1)]) \
            or await db.policy_versions.find_one({"slug": slug}, sort=[("version", -1)])
        rows.append({**m, "version": v["version"], "status": v["status"], "status_label": STATUS_LABEL[v["status"]], "body": v["body"],
                     "draft_date": _date(v.get("updated_at") or v.get("created_at")), "effective": v.get("effective_date") or "[EFFECTIVE DATE — set on approval]",
                     "version_id": str(v["_id"])})
    return {"policies": rows, "generated": datetime.now().strftime("%B %d, %Y")}


def sections(data: dict) -> list[str]:
    s = ["Part A — Review guide", "1. Purpose, status and how to use this pack", "2. Policy register", "3. Information AfroVending must supply",
         "4. Commissions, subscriptions, Stripe Connect, payouts, refunds, chargebacks and liability", "5. Outstanding legal questions by policy",
         "6. Questions by area of law", "7. Conflicts and inconsistencies", "8. Consolidated attorney review checklist", "Part B — Full policy drafts"]
    s += [f"B{i}. {p['title']} (version {p['version']})" for i, p in enumerate(data["policies"], 1)]
    s += ["Part C — Final legal review record"]
    return s


# ---------------- DOCX ----------------
def build_docx(data: dict, path: Path) -> None:
    from docx import Document
    from docx.enum.section import WD_SECTION
    from docx.enum.table import WD_TABLE_ALIGNMENT
    from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_BREAK, WD_COLOR_INDEX
    from docx.oxml import OxmlElement
    from docx.oxml.ns import qn
    from docx.shared import Pt, RGBColor, Cm

    INK, CLAY, RED = RGBColor(0x1F, 0x1A, 0x17), RGBColor(0xB4, 0x4A, 0x1C), RGBColor(0xB0, 0x1E, 0x1E)
    doc = Document()
    sec = doc.sections[0]
    sec.left_margin = sec.right_margin = Cm(2.2)
    sec.top_margin = sec.bottom_margin = Cm(2.0)
    st = doc.styles["Normal"]
    st.font.name, st.font.size = "Calibri", Pt(10.5)
    for name, size in (("Heading 1", 18), ("Heading 2", 14), ("Heading 3", 11.5)):
        h = doc.styles[name]
        h.font.name, h.font.size, h.font.color.rgb, h.font.bold = "Calibri", Pt(size), CLAY if name != "Heading 3" else INK, True

    def shade(cell, hexcolor):
        tcPr = cell._tc.get_or_add_tcPr()
        el = OxmlElement("w:shd")
        el.set(qn("w:val"), "clear"), el.set(qn("w:color"), "auto"), el.set(qn("w:fill"), hexcolor)
        tcPr.append(el)

    def runs(par, text, bold=False, size=None, color=None):
        for part in INLINE.split(text):
            if not part:
                continue
            b = bold
            if part.startswith("**") and part.endswith("**"):
                part, b = part[2:-2], True
            r = par.add_run(part.strip("`") if part.startswith("`") else part)
            r.bold = b
            if size:
                r.font.size = Pt(size)
            if color:
                r.font.color.rgb = color
            if INLINE.fullmatch(part) and part.startswith("["):
                r.font.highlight_color = WD_COLOR_INDEX.YELLOW
                r.bold = True
        return par

    def para(text="", bold=False, size=None, color=None, align=None, space=4):
        p = doc.add_paragraph()
        p.paragraph_format.space_after = Pt(space)
        if align:
            p.alignment = align
        return runs(p, text, bold, size, color)

    def table(rows, header=True, widths=None, fill="F3E9DD"):
        t = doc.add_table(rows=0, cols=len(rows[0]))
        t.style = "Table Grid"
        t.alignment = WD_TABLE_ALIGNMENT.CENTER
        if widths:
            t.autofit = False
            scale = 16.6 / sum(widths)
            widths = [w * scale for w in widths]
            for gc, w in zip(t._tbl.tblGrid.findall(qn("w:gridCol")), widths):
                gc.set(qn("w:w"), str(int(w * 567)))
        for ri, r in enumerate(rows):
            cells = t.add_row().cells
            for ci, val in enumerate(r):
                cells[ci].paragraphs[0].paragraph_format.space_after = Pt(0)
                runs(cells[ci].paragraphs[0], str(val), bold=header and ri == 0, size=9)
                if header and ri == 0:
                    shade(cells[ci], fill)
                if widths:
                    cells[ci].width = Cm(widths[ci])
        doc.add_paragraph().paragraph_format.space_after = Pt(2)
        return t

    def callout(text, fill="FFF4CC"):
        t = doc.add_table(rows=1, cols=1)
        t.style = "Table Grid"
        c = t.rows[0].cells[0]
        shade(c, fill)
        runs(c.paragraphs[0], text, size=9.5)
        doc.add_paragraph().paragraph_format.space_after = Pt(2)

    def box(label, lines=8):
        t = doc.add_table(rows=1 + lines, cols=1)
        t.style = "Table Grid"
        runs(t.rows[0].cells[0].paragraphs[0], label, bold=True, size=9.5)
        shade(t.rows[0].cells[0], "F3E9DD")
        for r in t.rows[1:]:
            r.height = Cm(0.8)
        doc.add_paragraph().paragraph_format.space_after = Pt(2)

    def field(par, instr):
        r = par.add_run()
        for kind, text in (("begin", None), (None, instr), ("separate", None), (None, "1"), ("end", None)):
            if kind:
                el = OxmlElement("w:fldChar")
                el.set(qn("w:fldCharType"), kind)
            elif text == instr:
                el = OxmlElement("w:instrText")
                el.set(qn("xml:space"), "preserve")
                el.text = f" {instr} "
            else:
                el = OxmlElement("w:t")
                el.text = text
            r._r.append(el)
        r.font.size = Pt(8)

    def page_break():
        doc.add_paragraph().add_run().add_break(WD_BREAK.PAGE)

    # Cover
    for _ in range(5):
        para()
    para(TITLE1, True, 20, INK, WD_ALIGN_PARAGRAPH.CENTER, 6)
    para(TITLE2, True, 16, CLAY, WD_ALIGN_PARAGRAPH.CENTER, 24)
    para(CONF.upper(), True, 13, RED, WD_ALIGN_PARAGRAPH.CENTER, 10)
    para(NOT_APPROVED, False, 10, RED, WD_ALIGN_PARAGRAPH.CENTER, 30)
    table([["Prepared for", "Legal counsel to AfroVending Online Marketplace LLC"], ["Website", "afrovending.com (United States)"],
           ["Policies included", "Seven marketplace policies, all at status Draft — Pending Legal Review"], ["Pack generated", data["generated"]],
           ["Contact", "info@afrovending.com"], ["Business address", "[BUSINESS ADDRESS]"]], header=False, widths=[4.5, 11])
    para("Distribution: internal and the reviewing attorney only, after the Super Admin approves external sharing.", size=9, align=WD_ALIGN_PARAGRAPH.CENTER)

    # Header/footer for the body section
    body = doc.add_section(WD_SECTION.NEW_PAGE)
    body.different_first_page_header_footer = False
    sec.different_first_page_header_footer = True
    body.header.is_linked_to_previous = False
    hp = body.header.paragraphs[0]
    runs(hp, f"{TITLE1} — Marketplace Legal Policy Review Pack", size=8, color=CLAY)
    body.footer.is_linked_to_previous = False
    fp = body.footer.paragraphs[0]
    fp.alignment = WD_ALIGN_PARAGRAPH.CENTER
    runs(fp, f"{CONF} · Not legally approved · Page ", size=8)
    field(fp, "PAGE")
    runs(fp, " of ", size=8)
    field(fp, "NUMPAGES")

    doc.add_heading("Table of contents", 1)
    for s in sections(data):
        p = para(s, bold=s.startswith("Part"), space=2)
        if not s.startswith("Part"):
            p.paragraph_format.left_indent = Cm(0.8)
    page_break()

    doc.add_heading("Part A — Review guide", 1)
    doc.add_heading("1. Purpose, status and how to use this pack", 2)
    para("This pack contains the complete current drafts of AfroVending's seven customer- and vendor-facing marketplace policies, prepared for attorney review before the marketplace launches in the United States. The initial legal context is Massachusetts law and applicable U.S. federal law.")
    callout("Status: every policy is at Draft — Pending Legal Review. None has been approved, published or shown to the public. The website currently displays 'This policy is being finalised' in place of each policy.")
    para("**How to read the drafts.** Text in [square brackets] is highlighted. It marks a placeholder for missing business information, or a clause flagged for legal confirmation. Question IDs (for example TOS-1) link Sections 5–8 to the clauses.")
    table([["Tag", "Area of law"]] + [list(x) for x in C.LEGEND], widths=[3, 12])
    para("**How approval works in the system.** After review, AfroVending's Super Admin records the reviewing attorney, the review date and notes in Policy Management, marks each change as Material or Non-material, sets the effective date, and then publishes. Approved versions are locked. Customers and vendors accept versioned policies through unchecked checkboxes, and each acceptance is recorded.")
    doc.add_heading("2. Policy register", 2)
    table([["#", "Policy", "Draft version", "Status", "Draft date", "Public URL", "Accepted by"]] +
          [[str(i), p["title"], f"v{p['version']}", p["status_label"], p["draft_date"], f"afrovending.com{p['path']}",
            {"customer": "Customers", "vendor": "Vendors", None: "— (notice)"}[p["acceptance"]]] for i, p in enumerate(data["policies"], 1)],
          widths=[0.7, 3.5, 1.6, 3.2, 2.4, 3.6, 2])
    doc.add_heading("3. Information AfroVending must supply", 2)
    for x in C.MISSING_INFO:
        para(f"[ ]  {x}", space=2)
    doc.add_heading("4. Commissions, subscriptions, Stripe Connect, payouts, refunds, chargebacks and liability", 2)
    callout("Features are labelled by their current status. Anything marked NOT operational must stay described as planned or unavailable until it has been verified.")
    table([["Topic", "What the drafts say", "Current status", "Questions"]] + [list(r) for r in C.COMMERCIAL], widths=[2.8, 5.6, 4.4, 2.8])
    doc.add_heading("5. Outstanding legal questions by policy", 2)
    for p in data["policies"]:
        qs = [q for q in C.QUESTIONS if q[1] == p["slug"]]
        doc.add_heading(f"{p['title']} (v{p['version']})", 3)
        table([["ID", "Clause", "Question for counsel", "Area"]] + [[q[0], q[2], q[3], q[4]] for q in qs], widths=[1.4, 1.4, 10.4, 2.4])
    doc.add_heading("6. Questions by area of law", 2)
    for tag, name in C.LEGEND:
        ids = [q[0] for q in C.QUESTIONS if tag in q[4]]
        para(f"**{name} {tag}:** {', '.join(ids) if ids else '—'}", space=3)
    doc.add_heading("7. Conflicts and inconsistencies", 2)
    table([["#", "Where", "Issue", "Suggested resolution"]] + [[str(i), *r] for i, r in enumerate(C.CONFLICTS, 1)], widths=[0.7, 3.3, 6.6, 5])
    doc.add_heading("8. Consolidated attorney review checklist", 2)
    table([["Done", "Review item", "Attorney notes"]] + [["[ ]", x, ""] for x in C.CHECKLIST], widths=[1.3, 8.8, 5.5])

    for i, p in enumerate(data["policies"], 1):
        page_break()
        if i == 1:
            doc.add_heading("Part B — Full policy drafts", 1)
        doc.add_heading(f"B{i}. {p['title']}", 2)
        table([["Version", f"{p['version']} (draft)"], ["Status", p["status_label"]], ["Draft date", p["draft_date"]],
               ["Effective date", p["effective"]], ["Public URL", f"afrovending.com{p['path']}"]], header=False, widths=[3.5, 12])
        for b in md_blocks(p["body"]):
            if b[0] == "h":
                doc.add_heading(b[2], 3 if b[1] == 2 else 3)
            elif b[0] == "p":
                para(b[1])
            elif b[0] == "li":
                pp = para(f"{b[3]}  {b[1]}" if b[3] else b[1], space=2)
                pp.paragraph_format.left_indent = Cm(0.6 * b[2])
                pp.paragraph_format.first_line_indent = Cm(-0.4) if b[3] else None
            elif b[0] == "table":
                table(b[1])
            elif b[0] == "callout":
                callout(b[1])
        box(f"Attorney comments and requested revisions — {p['title']}", 10)

    page_break()
    doc.add_heading("Part C — Final legal review record", 1)
    callout("To be completed by the reviewing attorney. Completing this record does not by itself publish any policy. AfroVending's Super Admin records the outcome in Policy Management.")
    table([["Field", "Entry"], ["Reviewing attorney (name)", ""], ["Law firm", ""], ["Bar admission(s)", ""], ["Email / telephone", ""],
           ["Review date(s)", ""], ["Pack generated", data["generated"]]], widths=[5, 10.6])
    table([["Policy", "Version reviewed", "Approve", "Approve with changes", "Revise and resubmit", "Material change?"]] +
          [[p["title"], f"v{p['version']}", "[ ]", "[ ]", "[ ]", "[ ] Yes  [ ] No"] for p in data["policies"]], widths=[4, 2, 1.8, 2.6, 2.6, 2.6])
    box("Recommendations", 10)
    box("Conditions or required changes before publication", 6)
    para("Attorney signature: ______________________________    Date: ______________")
    para("AfroVending authorised representative: ______________________________    Date: ______________")
    doc.save(path)


# ---------------- PDF ----------------
def build_pdf(data: dict, path: Path) -> None:
    from xml.sax.saxutils import escape

    from reportlab.lib import colors
    from reportlab.lib.pagesizes import LETTER
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import cm
    from reportlab.platypus import KeepTogether, PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

    clay, ink, red, sand = colors.HexColor("#B44A1C"), colors.HexColor("#1F1A17"), colors.HexColor("#B01E1E"), colors.HexColor("#F3E9DD")
    ss = getSampleStyleSheet()
    N = ParagraphStyle("n", parent=ss["Normal"], fontName="Helvetica", fontSize=9.5, leading=13, spaceAfter=4)
    S = ParagraphStyle("s", parent=N, fontSize=8.5, leading=11, spaceAfter=0)
    H1 = ParagraphStyle("h1", parent=N, fontName="Helvetica-Bold", fontSize=17, leading=21, textColor=clay, spaceBefore=4, spaceAfter=10)
    H2 = ParagraphStyle("h2", parent=H1, fontSize=13, leading=16, spaceBefore=10, spaceAfter=6)
    H3 = ParagraphStyle("h3", parent=H1, fontSize=10.5, leading=13, textColor=ink, spaceBefore=8, spaceAfter=4)
    C1 = ParagraphStyle("c", parent=N, alignment=1)
    W = LETTER[0] - 4.4 * cm

    def fmt(text: str) -> str:
        out = []
        for part in INLINE.split(text):
            if not part:
                continue
            if part.startswith("**") and part.endswith("**"):
                out.append(f"<b>{escape(part[2:-2])}</b>")
            elif part.startswith("`"):
                out.append(f"<font face='Courier'>{escape(part.strip('`'))}</font>")
            elif part.startswith("[") and INLINE.fullmatch(part):
                out.append(f"<font backColor='#FFE45C'><b>{escape(part)}</b></font>")
            else:
                out.append(escape(part))
        return "".join(out).replace("•", "&bull;")

    def P(text, style=N):
        return Paragraph(fmt(text), style)

    def tbl(rows, widths=None, header=True):
        widths = [W * w / sum(widths) for w in widths] if widths else None
        t = Table([[P(str(c), S) for c in r] for r in rows], colWidths=widths, repeatRows=1 if header else 0)
        st = [("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#C9B9A6")), ("VALIGN", (0, 0), (-1, -1), "TOP"),
              ("LEFTPADDING", (0, 0), (-1, -1), 4), ("RIGHTPADDING", (0, 0), (-1, -1), 4)]
        if header:
            st.append(("BACKGROUND", (0, 0), (-1, 0), sand))
        t.setStyle(TableStyle(st))
        return [t, Spacer(1, 6)]

    def callout(text, fill="#FFF4CC"):
        t = Table([[P(text, S)]], colWidths=[W])
        t.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), colors.HexColor(fill)), ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#C9B9A6")),
                               ("LEFTPADDING", (0, 0), (-1, -1), 6), ("TOPPADDING", (0, 0), (-1, -1), 5), ("BOTTOMPADDING", (0, 0), (-1, -1), 5)]))
        return [t, Spacer(1, 6)]

    def box(label, lines=8):
        t = Table([[P(f"**{label}**", S)]] + [[""]] * lines, colWidths=[W], rowHeights=[None] + [0.75 * cm] * lines)
        t.setStyle(TableStyle([("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#C9B9A6")), ("BACKGROUND", (0, 0), (-1, 0), sand)]))
        return [KeepTogether([t]), Spacer(1, 6)]

    story = [Spacer(1, 5 * cm), P(f"**{TITLE1}**", ParagraphStyle("t1", parent=C1, fontSize=19, leading=24, textColor=ink)),
             P(f"**{TITLE2}**", ParagraphStyle("t2", parent=C1, fontSize=15, leading=20, textColor=clay, spaceAfter=24)),
             P(f"**{CONF.upper()}**", ParagraphStyle("t3", parent=C1, fontSize=12, textColor=red, spaceAfter=8)),
             P(NOT_APPROVED, ParagraphStyle("t4", parent=C1, textColor=red, spaceAfter=24))]
    story += tbl([["Prepared for", "Legal counsel to AfroVending Online Marketplace LLC"], ["Website", "afrovending.com (United States)"],
                  ["Policies included", "Seven marketplace policies, all at status Draft — Pending Legal Review"], ["Pack generated", data["generated"]],
                  ["Contact", "info@afrovending.com"], ["Business address", "[BUSINESS ADDRESS]"]], [4.5, 11], header=False)
    story += [P("Distribution: internal and the reviewing attorney only, after the Super Admin approves external sharing.", ParagraphStyle("t5", parent=C1, fontSize=8.5)), PageBreak()]
    story.append(P("Table of contents", H1))
    for s in sections(data):
        story.append(P(f"**{s}**" if s.startswith("Part") else s, ParagraphStyle("toc", parent=N, leftIndent=0 if s.startswith("Part") else 14, spaceAfter=2)))
    story += [PageBreak(), P("Part A — Review guide", H1), P("1. Purpose, status and how to use this pack", H2),
              P("This pack contains the complete current drafts of AfroVending's seven customer- and vendor-facing marketplace policies, prepared for attorney review before the marketplace launches in the United States. The initial legal context is Massachusetts law and applicable U.S. federal law.")]
    story += callout("Status: every policy is at Draft — Pending Legal Review. None has been approved, published or shown to the public. The website currently displays 'This policy is being finalised' in place of each policy.")
    story.append(P("**How to read the drafts.** Text in [square brackets] is highlighted. It marks a placeholder for missing business information, or a clause flagged for legal confirmation. Question IDs (for example TOS-1) link Sections 5–8 to the clauses."))
    story += tbl([["Tag", "Area of law"]] + [list(x) for x in C.LEGEND], [3, 12])
    story.append(P("**How approval works in the system.** After review, AfroVending's Super Admin records the reviewing attorney, the review date and notes in Policy Management, marks each change as Material or Non-material, sets the effective date, and then publishes. Approved versions are locked. Customers and vendors accept versioned policies through unchecked checkboxes, and each acceptance is recorded."))
    story.append(P("2. Policy register", H2))
    story += tbl([["#", "Policy", "Draft version", "Status", "Draft date", "Public URL", "Accepted by"]] +
                 [[str(i), p["title"], f"v{p['version']}", p["status_label"], p["draft_date"], f"afrovending.com{p['path']}",
                   {"customer": "Customers", "vendor": "Vendors", None: "— (notice)"}[p["acceptance"]]] for i, p in enumerate(data["policies"], 1)],
                 [0.7, 3.5, 1.6, 3.2, 2.4, 3.6, 2])
    story.append(P("3. Information AfroVending must supply", H2))
    story += [P(f"[ ]  {x}", ParagraphStyle("ck", parent=N, spaceAfter=2)) for x in C.MISSING_INFO]
    story.append(P("4. Commissions, subscriptions, Stripe Connect, payouts, refunds, chargebacks and liability", H2))
    story += callout("Features are labelled by their current status. Anything marked NOT operational must stay described as planned or unavailable until it has been verified.")
    story += tbl([["Topic", "What the drafts say", "Current status", "Questions"]] + [list(r) for r in C.COMMERCIAL], [2.8, 5.6, 4.4, 2.8])
    story.append(P("5. Outstanding legal questions by policy", H2))
    for p in data["policies"]:
        story.append(P(f"{p['title']} (v{p['version']})", H3))
        story += tbl([["ID", "Clause", "Question for counsel", "Area"]] + [[q[0], q[2], q[3], q[4]] for q in C.QUESTIONS if q[1] == p["slug"]], [1.4, 1.4, 10.4, 2.4])
    story.append(P("6. Questions by area of law", H2))
    for tag, name in C.LEGEND:
        ids = [q[0] for q in C.QUESTIONS if tag in q[4]]
        story.append(P(f"**{name} {tag}:** {', '.join(ids) if ids else '—'}"))
    story.append(P("7. Conflicts and inconsistencies", H2))
    story += tbl([["#", "Where", "Issue", "Suggested resolution"]] + [[str(i), *r] for i, r in enumerate(C.CONFLICTS, 1)], [0.7, 3.3, 6.6, 5])
    story.append(P("8. Consolidated attorney review checklist", H2))
    story += tbl([["Done", "Review item", "Attorney notes"]] + [["[ ]", x, ""] for x in C.CHECKLIST], [1.3, 8.8, 5.5])
    for i, p in enumerate(data["policies"], 1):
        story.append(PageBreak())
        if i == 1:
            story.append(P("Part B — Full policy drafts", H1))
        story.append(P(f"B{i}. {p['title']}", H2))
        story += tbl([["Version", f"{p['version']} (draft)"], ["Status", p["status_label"]], ["Draft date", p["draft_date"]],
                      ["Effective date", p["effective"]], ["Public URL", f"afrovending.com{p['path']}"]], [3.5, 12], header=False)
        for b in md_blocks(p["body"]):
            if b[0] == "h":
                story.append(P(b[2], H3))
            elif b[0] == "p":
                story.append(P(b[1]))
            elif b[0] == "li":
                story.append(Paragraph(fmt(b[1]), ParagraphStyle("li", parent=N, leftIndent=14 * b[2], bulletIndent=14 * b[2] - 10, spaceAfter=2),
                                       bulletText=b[3] or None))
            elif b[0] == "table":
                story += tbl(b[1], [1] * len(b[1][0]))
            elif b[0] == "callout":
                story += callout(b[1])
        story += box(f"Attorney comments and requested revisions — {p['title']}", 10)
    story += [PageBreak(), P("Part C — Final legal review record", H1)]
    story += callout("To be completed by the reviewing attorney. Completing this record does not by itself publish any policy. AfroVending's Super Admin records the outcome in Policy Management.")
    story += tbl([["Field", "Entry"], ["Reviewing attorney (name)", ""], ["Law firm", ""], ["Bar admission(s)", ""], ["Email / telephone", ""],
                  ["Review date(s)", ""], ["Pack generated", data["generated"]]], [5, 10.6])
    story += tbl([["Policy", "Version reviewed", "Approve", "Approve with changes", "Revise and resubmit", "Material change?"]] +
                 [[p["title"], f"v{p['version']}", "[ ]", "[ ]", "[ ]", "[ ] Yes  [ ] No"] for p in data["policies"]], [4, 2, 1.8, 2.6, 2.6, 2.6])
    story += box("Recommendations", 10) + box("Conditions or required changes before publication", 6)
    story += [Spacer(1, 10), P("Attorney signature: ______________________________    Date: ______________"),
              P("AfroVending authorised representative: ______________________________    Date: ______________")]

    def deco(canvas, doc_):
        if doc_.page == 1:
            return
        canvas.saveState()
        canvas.setFont("Helvetica", 7.5)
        canvas.setFillColor(clay)
        canvas.drawString(2.2 * cm, LETTER[1] - 1.3 * cm, f"{TITLE1} — Marketplace Legal Policy Review Pack")
        canvas.setFillColor(ink)
        canvas.drawCentredString(LETTER[0] / 2, 1.1 * cm, f"{CONF} · Not legally approved · Page {doc_.page}")
        canvas.restoreState()

    SimpleDocTemplate(str(path), pagesize=LETTER, leftMargin=2.2 * cm, rightMargin=2.2 * cm, topMargin=2 * cm, bottomMargin=2 * cm,
                      title=TITLE2.title(), author="AfroVending Online Marketplace LLC", subject=CONF).build(story, onFirstPage=deco, onLaterPages=deco)
