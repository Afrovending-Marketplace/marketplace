import io
from html import escape

from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

RED, NAVY, LINE, SAND = (colors.HexColor(c) for c in ("#D40000", "#1E2A38", "#E6DFD3", "#FAF7F2"))


def build_slip(vo: dict, lines: list[tuple[dict, int]], shipment: dict | None) -> bytes:
    """US Letter packing slip. No prices, totals, taxes, commissions or payment data by design."""
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=letter, title=f"Packing slip {vo['order_number']}", leftMargin=40, rightMargin=40, topMargin=36)
    st = getSampleStyleSheet()
    head = Table([[Paragraph("<font color='white' size=18><b>AFROVENDING</b></font><br/><font color='white' size=8>From Culture to Commerce · "
                             "www.afrovending.com · info@afrovending.com</font>", st["Normal"]),
                   Paragraph("<font color='white' size=14><b>PACKING SLIP</b></font>", st["Normal"])]], colWidths=[382, 150])
    head.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), NAVY), ("LINEBELOW", (0, 0), (-1, -1), 3, RED),
                              ("PADDING", (0, 0), (-1, -1), 10), ("VALIGN", (0, 0), (-1, -1), "MIDDLE")]))
    a = vo.get("shipping_address") or {}
    if vo.get("fulfillment_type") == "pickup":
        to = f"<b>{escape(a.get('full_name', ''))}</b><br/>Local pickup at: {escape((vo.get('shipping_method') or {}).get('pickup_address', ''))}"
    else:
        to = "<br/>".join(escape(x) for x in [f"<b>{a.get('full_name', '')}</b>", a.get("line1", ""), a.get("line2", ""),
                                               f"{a.get('city', '')}, {a.get('region', '')} {a.get('postal_code', '')}".strip(", "), a.get("country", "")] if x)
        to = to.replace("&lt;b&gt;", "<b>").replace("&lt;/b&gt;", "</b>")
    pkg = f"Package: {escape(shipment['carrier_name'])} {escape(shipment['tracking_number'])}" if shipment else "Package: items still to be sent"
    meta = Table([[Paragraph(f"<b>Order</b> {escape(vo['order_number'])}<br/><b>Order date</b> {vo['created_at'].strftime('%B %d, %Y')}<br/>"
                             f"<b>Sold by</b> {escape(vo['vendor_name'])}<br/>{pkg}", st["Normal"]),
                   Paragraph(f"<b>{'Collected by' if vo.get('fulfillment_type') == 'pickup' else 'Ship to'}</b><br/>{to}", st["Normal"])]], colWidths=[266, 266])
    meta.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("BOX", (1, 0), (1, 0), 0.6, LINE), ("PADDING", (0, 0), (-1, -1), 8)]))
    rows = [["Item", "Variant", "SKU", "Qty"]] + [[Paragraph(escape(it["title"]), st["Normal"]), "" if it.get("label") == "Default" else it.get("label", ""),
                                                   it.get("sku", ""), str(q)] for it, q in lines]
    items = Table(rows, colWidths=[250, 120, 112, 50], repeatRows=1)
    items.setStyle(TableStyle([("GRID", (0, 0), (-1, -1), 0.4, LINE), ("BACKGROUND", (0, 0), (-1, 0), SAND), ("FONTSIZE", (0, 0), (-1, -1), 9),
                               ("ALIGN", (3, 0), (3, -1), "CENTER"), ("VALIGN", (0, 0), (-1, -1), "MIDDLE")]))
    total = sum(q for _, q in lines)
    parts = [head, Spacer(1, 14), meta, Spacer(1, 14), items, Spacer(1, 6), Paragraph(f"Items in this package: <b>{total}</b>", st["Normal"]), Spacer(1, 18),
             Paragraph("<b>Returns</b> — Most items can be returned within the return window shown on your order. Start a return from "
                       "<b>My account → Orders</b> at www.afrovending.com, or email info@afrovending.com with your order number.", st["Normal"]),
             Spacer(1, 10), Paragraph(f"Thank you for supporting {escape(vo['vendor_name'])} on AfroVending.", st["Italic"])]
    doc.build(parts)
    return buf.getvalue()
