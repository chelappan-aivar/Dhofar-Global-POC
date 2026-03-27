import os
import random
import datetime
import uuid
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.pdfgen import canvas
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

# ============================================================
# FONT SETUP (JAPANESE + FALLBACK)
# ============================================================

HAS_JAPANESE_FONT = False
JAPANESE_FONT = "Helvetica"  # Fallback, will not render Japanese properly

# Try a couple of common Noto Japanese fonts
for font_name, font_path in [
    ("NotoSansJP", "NotoSansJP-VariableFont_wght.ttf"),
    ("NotoSansCJKjp", "fonts/NotoSansCJKjp-Regular.ttf"),
]:
    try:
        pdfmetrics.registerFont(TTFont(font_name, font_path))
        JAPANESE_FONT = font_name
        HAS_JAPANESE_FONT = True
        break
    except Exception:
        continue

if not HAS_JAPANESE_FONT:
    print(
        "Warning: Japanese font not found. "
        "Place NotoSansJP-Regular.ttf in the working folder "
        "or fonts/NotoSansCJKjp-Regular.ttf in a 'fonts' directory "
        "for proper Japanese rendering."
    )

# ============================================================
# CONFIGURATION
# ============================================================

NUM_TRANSACTIONS = 5
OUTPUT_DIR = "simulated_data_lake"
CHAOS_RATE = 0.5  # 5% of invoices will have issues

# Mock Data: Global Vendors
VENDORS = [
    {
        "name": "TechFlow Systems",
        "country": "USA",
        "currency": "USD",
        "address": "123 Silicon Blvd, San Jose, CA 95134",
        "header_title": "Invoice",
        "tagline": "High Performance Compute Solutions",
        "items": [
            {"sku": "TF-SRV-4U", "desc": "Server Rack Mount 4U", "price_range": (250, 550), "currency": "USD"},
            {"sku": "TF-SSD-100TB", "desc": "100TB SSD Storage Unit", "price_range": (900, 1300), "currency": "USD"},
            {"sku": "TF-FOC-100M", "desc": "Fiber Optic Cable (100m)", "price_range": (60, 160), "currency": "USD"},
        ],
    },
    {
        "name": "Nordic Chipsets AB",
        "country": "Sweden",
        "currency": "SEK",
        "address": "Fjordgatan 99, 116 45 Stockholm",
        "header_title": "Faktura",
        "tagline": "Precision Silicon from the Nordics",
        "items": [
            {"sku": "NC-SSD-100TB", "desc": "100TB SSD Storage Unit", "price_range": (9500, 12500), "currency": "SEK"},
            {"sku": "NC-FOC-100M", "desc": "Fiber Optic Cable (100m)", "price_range": (600, 1400), "currency": "SEK"},
            {"sku": "NC-SW-48P", "desc": "Enterprise Switch 48-Port", "price_range": (17000, 26000), "currency": "SEK"},
        ],
    },
    {
        "name": "Nippon Logic Ltd - 日本",
        "country": "Japan",
        "currency": "JPY",
        "address": "4-2-8 Shibakoen, Minato City, Tokyo",
        "header_title": "請求書",
        "tagline": "ハイパフォーマンス半導体ソリューション",
        "items": [
            {"sku": "NL-SRV-4U", "desc": "Server Rack Mount 4U", "price_range": (28000, 52000), "currency": "JPY"},
            {"sku": "NL-FOC-100M", "desc": "Fiber Optic Cable (100m)", "price_range": (5500, 14500), "currency": "JPY"},
            {"sku": "NL-FAN-MOD", "desc": "Cooling Fan Module", "price_range": (9000, 19000), "currency": "JPY"},
        ],
    },
    {
        "name": "Berlin Hardware GmbH",
        "country": "Germany",
        "currency": "EUR",
        "address": "Alexanderplatz 1, 10178 Berlin",
        "header_title": "Rechnung",
        "tagline": "Infrastruktur & Netzwerktechnik",
        "items": [
            {"sku": "BH-SRV-4U", "desc": "Server Rack Mount 4U", "price_range": (230, 520), "currency": "EUR"},
            {"sku": "BH-SSD-100TB", "desc": "100TB SSD Storage Unit", "price_range": (850, 1250), "currency": "EUR"},
            {"sku": "BH-SW-48P", "desc": "Enterprise Switch 48-Port", "price_range": (1600, 2600), "currency": "EUR"},
        ],
    },
    {
        "name": "Mumbai Micro Devices",
        "country": "India",
        "currency": "INR",
        "address": "Unit 402, Andheri East, Mumbai 400069",
        "header_title": "TAX INVOICE",
        "tagline": "Semiconductor & Datacenter Components",
        "items": [
            {"sku": "MM-FOC-100M", "desc": "Fiber Optic Cable (100m)", "price_range": (4200, 9800), "currency": "INR"},
            {"sku": "MM-FAN-MOD", "desc": "Cooling Fan Module", "price_range": (8200, 16500), "currency": "INR"},
            {"sku": "MM-SW-48P", "desc": "Enterprise Switch 48-Port", "price_range": (120000, 210000), "currency": "INR"},
        ],
    },
]

# Mock Data: Buying Companies (buyers can be in different countries)
BUYERS = [
    {"name": "Global Tech Corp", "country": "USA", "currency": "USD"},
    {"name": "Global Tech Europe GmbH", "country": "Germany", "currency": "EUR"},
    {"name": "Global Tech India Pvt Ltd", "country": "India", "currency": "INR"},
    {"name": "Global Tech Nordics AB", "country": "Sweden", "currency": "SEK"},
    {"name": "Global Tech Japan KK", "country": "Japan", "currency": "JPY"},
]

# Mock Data: Items (generic, mostly unused now because we use vendor catalogs)
ITEMS = [
    {"desc": "Server Rack Mount 4U", "price_range": (200, 500), "currency": "USD"},
    {"desc": "100TB SSD Storage Unit", "price_range": (800, 1200), "currency": "USD"},
    {"desc": "Fiber Optic Cable (100m)", "price_range": (50, 150), "currency": "USD"},
    {"desc": "Cooling Fan Module", "price_range": (100, 200), "currency": "USD"},
    {"desc": "Enterprise Switch 48-Port", "price_range": (1500, 2500), "currency": "USD"},
]

# Tax configuration per vendor country (used primarily for invoices)
DEFAULT_TAX_RATE = 0.10
TAX_RATES = {
    "USA": 0.08,
    "Sweden": 0.25,
    "Japan": 0.10,
    "Germany": 0.19,
    "India": 0.18,
}

# FX configuration: convert vendor currency amounts to a home/company currency
HOME_CURRENCY = "USD"
# Assume primary buying entity is US-based; used to decide if FX is needed
HOME_COUNTRY = "USA"
# Very rough, static FX just for simulation purposes
FX_RATES_TO_HOME = {
    "USD": 1.0,
    "SEK": 0.095,
    "JPY": 0.009,
    "EUR": 1.10,
    "INR": 0.012,
}

# Ensure output directories exist
os.makedirs(f"{OUTPUT_DIR}/incoming", exist_ok=True)

# ============================================================
# STYLES
# ============================================================

styles = getSampleStyleSheet()
style_normal = styles["Normal"]
style_heading = styles["Heading1"]
style_right = ParagraphStyle(name='RightAlign', parent=styles['Normal'], alignment=2)
style_bold = ParagraphStyle(name='Bold', parent=styles['Normal'], fontName='Helvetica-Bold')

# Japanese-capable paragraph style (or Helvetica as fallback)
jp_style = ParagraphStyle(
    name='JP',
    parent=styles['Normal'],
    fontName=JAPANESE_FONT,
)

# Section heading style for items / totals blocks
section_heading_style = ParagraphStyle(
    name="SectionHeading",
    parent=styles['Heading2'],
    fontSize=11,
    leading=13,
    spaceBefore=8,
    spaceAfter=4,
)

# Small meta text style
meta_style = ParagraphStyle(
    'Meta',
    parent=styles['Normal'],
    alignment=2,
    fontSize=9,
    leading=11,
)

# ============================================================
# HEADER & FOOTER DRAWING FUNCTIONS
# ============================================================

def draw_header_footer(c, doc, title_text, company_name="Global Tech Corporation"):
    c.saveState()
    # Top bar
    c.setFillColor(colors.HexColor("#2C3E50"))
    c.rect(0, A4[1] - 28 * mm, A4[0], 28 * mm, fill=1, stroke=0)

    # Main company title
    c.setFillColor(colors.white)
    c.setFont("Helvetica-Bold", 16)
    c.drawString(15 * mm, A4[1] - 16 * mm, company_name)

    # Sub text (right)
    c.setFont("Helvetica", 9)
    c.drawRightString(A4[0] - 15 * mm, A4[1] - 16 * mm, "Procurement Division | HQ: San Francisco, CA")

    # Document title
    c.setFillColor(colors.HexColor("#2C3E50"))
    c.setFont("Helvetica-Bold", 22)
    c.drawString(15 * mm, A4[1] - 42 * mm, title_text)

    # Footer
    c.setFillColor(colors.grey)
    c.setFont("Helvetica-Oblique", 8)
    c.drawCentredString(A4[0] / 2, 10 * mm, "Confidential Document - Generated for Internal Use Only")
    c.restoreState()


def draw_vendor_header(c, doc, title_text, vendor):
    c.saveState()
    country = vendor.get("country", "")
    name = vendor.get("name", "Vendor")
    header_title = vendor.get("header_title", title_text)
    tagline = vendor.get("tagline", None)

    # Country-specific background color
    if country == "India":
        bg_color = colors.HexColor("#1B5E20")
    elif country == "Germany":
        bg_color = colors.HexColor("#B71C1C")
    elif country == "Sweden":
        bg_color = colors.HexColor("#0D47A1")
    elif country == "Japan":
        bg_color = colors.HexColor("#4A148C")
    else:
        bg_color = colors.HexColor("#2C3E50")

    # Top bar
    c.setFillColor(bg_color)
    c.rect(0, A4[1] - 28 * mm, A4[0], 28 * mm, fill=1, stroke=0)
    c.setFillColor(colors.white)

    # Vendor name (Japanese-capable font if needed)
    if country == "Japan" and HAS_JAPANESE_FONT:
        c.setFont(JAPANESE_FONT, 16)
    else:
        c.setFont("Helvetica-Bold", 16)
    c.drawString(15 * mm, A4[1] - 16 * mm, name)

    # Country on right
    c.setFont("Helvetica", 10)
    c.drawRightString(A4[0] - 15 * mm, A4[1] - 16 * mm, country)

    # Header title (Invoice / 請求書 etc.)
    c.setFillColor(bg_color)
    if country == "Japan" and HAS_JAPANESE_FONT:
        c.setFont(JAPANESE_FONT, 20)
    else:
        c.setFont("Helvetica-Bold", 20)
    c.drawString(15 * mm, A4[1] - 42 * mm, header_title)

    # Tagline if available
    if tagline:
        if country == "Japan" and HAS_JAPANESE_FONT:
            c.setFont(JAPANESE_FONT, 9)
        else:
            c.setFont("Helvetica", 9)
        c.setFillColor(colors.white)
        c.drawString(15 * mm, A4[1] - 49 * mm, tagline)

    # Footer
    c.setFillColor(colors.grey)
    c.setFont("Helvetica-Oblique", 8)
    c.drawCentredString(A4[0] / 2, 10 * mm, "Auto-generated commercial invoice")
    c.restoreState()


def create_po_template(c, doc):
    draw_header_footer(c, doc, "PURCHASE ORDER")


def create_inv_template(c, doc):
    draw_header_footer(c, doc, "COMMERCIAL INVOICE", company_name="Vendor Invoice")


def create_grn_template(c, doc):
    draw_header_footer(c, doc, "GOODS RECEIPT NOTE")

# ============================================================
# CONTENT GENERATION HELPERS
# ============================================================

def create_info_table(left_data, right_data):
    """Creates a 2-column layout for address/info details"""
    data = [[left_data, right_data]]
    t = Table(data, colWidths=[90 * mm, 90 * mm])
    t.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('LEFTPADDING', (0, 0), (-1, -1), 0),
        ('RIGHTPADDING', (0, 0), (-1, -1), 0),
    ]))
    return t


def get_invoice_layout(vendor):
    name = vendor.get("name", "")
    country = vendor.get("country", "")

    if "Nordic Chipsets" in name:
        columns = ["#", "SKU", "Nordic Item", "Qty", "Unit", "Line Total"]
        col_widths = [20 * mm, 33 * mm, 50 * mm, 15 * mm, 30 * mm, 30 * mm]
        header_color = colors.HexColor("#0D47A1")
    elif "Nippon Logic" in name:
        columns = ["通し番号", "在庫管理番号", "品目", "数量", "単価", "金額"]
        col_widths = [20 * mm, 33 * mm, 50 * mm, 15 * mm, 30 * mm, 30 * mm]
        header_color = colors.HexColor("#4A148C")
    elif "Berlin Hardware" in name:
        columns = ["Pos.", "SKU", "Artikel", "Menge", "Einzelpreis", "Gesamt"]
        col_widths = [20 * mm, 33 * mm, 50 * mm, 15 * mm, 30 * mm, 30 * mm]
        header_color = colors.HexColor("#B71C1C")
    elif "Mumbai Micro" in name:
        columns = ["#", "SKU", "Item Description", "Qty", "Rate", "Amount"]
        col_widths = [20 * mm, 33 * mm, 50 * mm, 15 * mm, 30 * mm, 30 * mm]
        header_color = colors.HexColor("#1B5E20")
    else:
        columns = ["#", "SKU", "Description", "Qty", "Unit Price", "Total"]
        col_widths = [20 * mm, 33 * mm, 50 * mm, 15 * mm, 30 * mm, 30 * mm]
        header_color = colors.HexColor("#2C3E50")

    return columns, col_widths, header_color


def format_currency(amount, currency):
    return f"{currency} {amount:,.2f}"


def format_date(d):
    if isinstance(d, (datetime.date, datetime.datetime)):
        return d.strftime("%Y-%m-%d")
    return str(d)

# ============================================================
# MAIN PDF GENERATOR
# ============================================================

def generate_pdf(filename, context, doc_type):
    doc = SimpleDocTemplate(
        filename,
        pagesize=A4,
        rightMargin=15 * mm,
        leftMargin=15 * mm,
        topMargin=50 * mm,
        bottomMargin=20 * mm,
    )

    elements = []

    # 1. Top Metadata Block (Right Aligned under title)
    date_str = format_date(context.get('date'))

    if doc_type == "PO":
        meta_text = (
            f"<b>PO Number:</b> {context['po_num']}<br/>"
            f"<b>Date:</b> {date_str}<br/>"
            f"<b>Currency:</b> {context['currency']}"
        )
        on_page_func = create_po_template
    elif doc_type == "INV":
        meta_text = (
            f"<b>Invoice #:</b> {context['inv_num']}<br/>"
            f"<b>Date:</b> {date_str}<br/>"
            f"<b>Ref PO:</b> {context['ref_po']}"
        )
        vendor = context["vendor"]

        def _inv_header(c, d, v=vendor, t="COMMERCIAL INVOICE"):
            draw_vendor_header(c, d, t, v)

        on_page_func = _inv_header
    else:  # GRN
        meta_text = (
            f"<b>GRN Ref:</b> {context['grn_num']}<br/>"
            f"<b>Date Received:</b> {date_str}<br/>"
            f"<b>PO Ref:</b> {context['ref_po']}"
        )
        on_page_func = create_grn_template

    elements.append(Paragraph(meta_text, meta_style))
    elements.append(Spacer(1, 6 * mm))

    # 2. Address / Party Sections
    if doc_type == "PO":
        left_html = (
            f"<b>VENDOR:</b><br/>{context['vendor']['name']}"
            f"<br/>{context['vendor']['address']}<br/>{context['vendor']['country']}"
        )
        buyer = context.get('buyer', {})
        right_html = (
            f"<b>SHIP TO:</b><br/>Global Tech Corp Warehouse A<br/>"
            f"4500 Technology Dr<br/>San Jose, CA 95134, USA<br/><br/>"
            f"<b>Buyer:</b> {buyer.get('name','Global Tech Corp')}"
        )
        elements.append(create_info_table(Paragraph(left_html, style_normal), Paragraph(right_html, style_normal)))

    elif doc_type == "INV":
        vendor = context['vendor']
        buyer = context.get('buyer', {})

        buyer_name = buyer.get('name', 'Buying Company')
        buyer_country = context.get('buyer_country', buyer.get('country', ''))
        vendor_country = vendor.get('country')

        # Use Japanese paragraph style for Japanese vendor/buyer blocks
        addr_style = jp_style if vendor_country == "Japan" else style_normal

        left_html = (
            f"<b>BILL TO:</b><br/>{buyer_name}<br/>{buyer_country}"
        )
        right_html = (
            f"<b>REMIT TO:</b><br/>{vendor['name']}<br/>{vendor['address']}<br/>{vendor['country']}"
        )

        elements.append(create_info_table(Paragraph(left_html, addr_style), Paragraph(right_html, addr_style)))

        # India-specific GST and buyer/shipping details
        if vendor_country == "India":
            gstin_vendor = context.get('gstin_vendor', '27ABCDE1234F1Z5')
            gstin_buyer = context.get('gstin_buyer', '29ABCDE1234F1Z6')
            place_of_supply = context.get('place_of_supply', buyer_country or 'Maharashtra (27)')
            buyer_name_detail = context.get('buyer_name', buyer_name)
            default_ship_to = f"{buyer_name_detail}, {buyer_country}" if buyer_country else buyer_name_detail
            ship_to = context.get('shipping_address', default_ship_to)

            left_block = (
                f"<b>GSTIN (Vendor):</b> {gstin_vendor}<br/>"
                f"<b>GSTIN (Buyer):</b> {gstin_buyer}<br/>"
                f"<b>Place of Supply:</b> {place_of_supply}"
            )
            right_block = (
                f"<b>Buyer:</b><br/>{buyer_name_detail}<br/><br/>"
                f"<b>Ship To:</b><br/>{ship_to}"
            )
            elements.append(Spacer(1, 3 * mm))
            elements.append(create_info_table(Paragraph(left_block, style_normal), Paragraph(right_block, style_normal)))

        # Germany-specific tax details
        if vendor_country == "Germany":
            ust_id_seller = context.get('ust_id_seller', 'DE9832343')
            ust_id_buyer = context.get('ust_id_buyer', 'DE87234223')
            seller_label = context.get('seller_label', 'Verkäufer')
            buyer_label = context.get('buyer_label', 'Käufer')

            left_block = (
                f"<b>{seller_label} USt-IdNr.:</b> {ust_id_seller}<br/>"
                f"<b>{buyer_label} USt-IdNr.:</b> {ust_id_buyer}"
            )
            right_block = (
                f"<b>Ort der Ausstellung:</b> Berlin<br/>"
                f"<b>Ausstellungsdatum:</b> {date_str}"
            )
            elements.append(Spacer(1, 3 * mm))
            elements.append(create_info_table(Paragraph(left_block, style_normal), Paragraph(right_block, style_normal)))

    else:  # GRN
        vendor = context.get('vendor') or {}
        v_name = vendor.get('name', 'External Vendor')
        v_country = vendor.get('country', '')

        left_html = (
            f"<b>RECEIVED FROM:</b><br/>{v_name}<br/>"
            f"External Carrier / Logistics<br/>Ref: Bill of Lading #99283"
        )

        # Vary GRN receiving location by vendor country
        if v_country == 'India':
            received_at = "Dock 2, Mumbai Warehouse"
        elif v_country == 'Germany':
            received_at = "Tor 5, Lagerhaus Berlin"
        elif v_country == 'Sweden':
            received_at = "Kaj 3, Stockholm Logistikcenter"
        elif v_country == 'Japan':
            received_at = "Bay 7, Tokyo Logistics Hub"
        else:
            received_at = "Dock 4, Warehouse A"

        right_html = (
            f"<b>RECEIVED AT:</b><br/>{received_at}<br/>"
            f"Received By: J. Smith"
        )
        elements.append(create_info_table(Paragraph(left_html, style_normal), Paragraph(right_html, style_normal)))

        # Additional GRN metadata row
        grn_meta_left = (
            "<b>Carrier:</b> External Logistics Provider<br/>"
            "<b>Receipt Condition:</b> Intact / As per PO"
        )
        grn_meta_right = (
            f"<b>GRN No:</b> {context['grn_num']}<br/>"
            f"<b>PO Ref:</b> {context['ref_po']}"
        )
        elements.append(Spacer(1, 3 * mm))
        elements.append(create_info_table(Paragraph(grn_meta_left, style_normal), Paragraph(grn_meta_right, style_normal)))

    elements.append(Spacer(1, 8 * mm))

    # 3. Section Heading for Items
    if doc_type == "PO":
        elements.append(Paragraph("Purchase Order Line Items", section_heading_style))
    elif doc_type == "INV":
        elements.append(Paragraph("Invoice Line Items", section_heading_style))
    else:
        elements.append(Paragraph("Received Items", section_heading_style))

    elements.append(Spacer(1, 2 * mm))

    # 4. Items Table
    if doc_type == "GRN":
        data = [["#", "SKU", "Description", "Qty Rcvd", "Inspection Status"]]
        col_widths = [10 * mm, 33 * mm, 80 * mm, 25 * mm, 30 * mm]
        header_color = colors.HexColor("#2C3E50")
    elif doc_type == "INV":
        columns, col_widths, header_color = get_invoice_layout(context["vendor"])
        data = [columns]
    else:  # PO
        data = [["#", "SKU", "Description", "Qty", "Unit Price", "Total"]]
        col_widths = [10 * mm, 33 * mm, 73 * mm, 18 * mm, 22 * mm, 20 * mm]
        header_color = colors.HexColor("#2C3E50")

    for i, item in enumerate(context['items'], 1):
        if doc_type == "GRN":
            desc_text = item['desc']
            desc_cell = Paragraph(desc_text, style_normal)
            row = [
                str(i),
                item.get('sku', ''),
                desc_cell,
                str(item['qty']),
                item.get('status', 'OK'),
            ]
        else:
            # Determine currency for the row
            row_currency = item.get('currency', context.get('currency', ''))
            if row_currency:
                unit_price_str = format_currency(item['unit_price'], row_currency)
                total_str = format_currency(item.get('total', 0), row_currency)
            else:
                unit_price_str = f"{item['unit_price']:.2f}"
                total_str = f"{item.get('total', 0):.2f}"
            desc_cell = Paragraph(item['desc'], style_normal)
            row = [
                str(i),
                item.get('sku', ''),
                desc_cell,
                str(item['qty']),
                unit_price_str,
                total_str,
            ]
        data.append(row)

    t = Table(data, colWidths=col_widths)

    vendor_country = context.get('vendor', {}).get('country') if doc_type == "INV" else None

    t_style = [
        ('BACKGROUND', (0, 0), (-1, 0), header_color),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('ALIGN', (1, 1), (1, -1), 'LEFT'),   # SKU left
        ('ALIGN', (2, 0), (2, -1), 'LEFT'),   # Description left
        ('FONTNAME', (0, 0), (-1, 0), JAPANESE_FONT if (doc_type == "INV" and vendor_country == "Japan" and HAS_JAPANESE_FONT) else 'Helvetica-Bold'),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 10),
        ('TOPPADDING', (0, 0), (-1, 0), 6),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor("#E0E0E0")),
    ]

    # Striping
    for i in range(1, len(data)):
        if i % 2 == 0:
            t_style.append(('BACKGROUND', (0, i), (-1, i), colors.HexColor("#F9F9F9")))

    if doc_type != "GRN":
        t_style.append(('ALIGN', (3, 1), (-1, -1), 'RIGHT'))  # Quantities & prices right

    t.setStyle(TableStyle(t_style))
    elements.append(t)
    elements.append(Spacer(1, 5 * mm))

    # 5. Totals (Not for GRN)
    if doc_type != "GRN":
        elements.append(Spacer(1, 4 * mm))
        elements.append(Paragraph("Totals Summary", section_heading_style))
        elements.append(Spacer(1, 2 * mm))

        tax_rate = context.get('tax_rate', DEFAULT_TAX_RATE)
        tax_pct_label = int(tax_rate * 100)
        total_data = [
            ["Subtotal:", format_currency(context['subtotal'], context['currency'])],
            [f"Tax ({tax_pct_label}%):", format_currency(context['tax'], context['currency'])],
            ["TOTAL:", format_currency(context['grand_total'], context['currency'])],
        ]

        home_currency = context.get('home_currency')
        fx_rate = context.get('fx_rate')
        grand_total_home = context.get('grand_total_home')
        if home_currency and fx_rate and grand_total_home is not None:
            fx_label = f"Total in {home_currency} (FX {fx_rate:.4f})"
            total_data.append([
                fx_label,
                format_currency(grand_total_home, home_currency)
            ])

        t_totals = Table(total_data, colWidths=[145 * mm, 35 * mm])
        t_totals.setStyle(TableStyle([
            ('ALIGN', (0, 0), (-1, -1), 'RIGHT'),
            ('FONTNAME', (0, -1), (-1, -1), 'Helvetica-Bold'),  # Bold last row
            ('BACKGROUND', (0, -1), (-1, -1), colors.HexColor("#E8E8E8")),
            ('BOX', (0, -1), (-1, -1), 0.75, colors.black),
            ('TOPPADDING', (0, 0), (-1, -1), 4),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
        ]))
        elements.append(t_totals)

    # 6. Chaos Notes / Footer Text
    elements.append(Spacer(1, 8 * mm))
    if context.get('note'):
        note_style = ParagraphStyle(
            'ChaosNote',
            parent=styles['Normal'],
            textColor=colors.red,
            fontName='Helvetica-Bold',
        )
        elements.append(Paragraph(f"NOTE: {context['note']}", note_style))

    # Country-specific invoice footer blocks
    if doc_type == "INV" and vendor_country == "India":
        payment_terms = context.get('payment_terms', 'Payment due within 30 days from invoice date.')
        bank_details = context.get('bank_details', 'Bank: ICICI Bank, A/C: 2715500356, IFSC: ICIC045F, Branch: Mumbai')
        footer_note = context.get('footer_note', 'Goods once sold will not be taken back. Subject to Maharashtra jurisdiction.')

        elements.append(Paragraph(f"<b>Payment Terms:</b> {payment_terms}", style_normal))
        elements.append(Paragraph(f"<b>Bank Details:</b> {bank_details}", style_normal))
        elements.append(Paragraph(footer_note, style_normal))

    if doc_type == "INV" and vendor_country == "Germany":
        de_payment_terms = context.get('de_payment_terms', 'Zahlbar innerhalb von 14 Tagen ohne Abzug.')
        de_footer_note = context.get('de_footer_note', 'Es gelten unsere allgemeinen Geschäftsbedingungen.')

        elements.append(Paragraph(f"<b>Zahlungsziel:</b> {de_payment_terms}", style_normal))
        elements.append(Paragraph(de_footer_note, style_normal))

    if doc_type == "INV" and vendor_country == "USA":
        us_payment_terms = context.get('us_payment_terms', 'Payment due within 30 days. Please remit in USD.')
        us_footer_note = context.get('us_footer_note', 'Thank you for your business.')

        elements.append(Paragraph(f"<b>Payment Terms:</b> {us_payment_terms}", style_normal))
        elements.append(Paragraph(us_footer_note, style_normal))

    if doc_type == "INV" and vendor_country == "Sweden":
        se_payment_terms = context.get('se_payment_terms', 'Betalningsvillkor: 30 dagar netto.')
        se_footer_note = context.get('se_footer_note', 'Org.nr och momsregistreringsnummer finns angivna ovan.')

        elements.append(Paragraph(f"<b>Betalningsvillkor:</b> {se_payment_terms}", style_normal))
        elements.append(Paragraph(se_footer_note, style_normal))

    if doc_type == "INV" and vendor_country == "Japan":
        jp_payment_terms = context.get(
            'jp_payment_terms',
            'お支払条件：請求書受領後30日以内にお振込みください。'
        )
        jp_footer_note = context.get(
            'jp_footer_note',
            '本請求書に関するお問い合わせは経理部までご連絡ください。'
        )

        # Use Japanese style for footer so characters render correctly
        elements.append(Paragraph(jp_payment_terms, jp_style))
        elements.append(Paragraph(jp_footer_note, jp_style))

    if doc_type == "GRN":
        elements.append(Spacer(1, 10 * mm))
        elements.append(Paragraph(
            "Certification: I hereby certify that the goods listed above have been received and inspected.",
            style_normal,
        ))
        elements.append(Spacer(1, 15 * mm))
        elements.append(Paragraph("Signed: __________________________", style_normal))

    # Build PDF
    doc.build(elements, onFirstPage=on_page_func, onLaterPages=on_page_func)

# ============================================================
# DATASET GENERATOR
# ============================================================

def generate_dataset():
    print(f"Generating {NUM_TRANSACTIONS} ReportLab PDF transaction sets...")

    for i in range(NUM_TRANSACTIONS):
        # 1. Base Logic
        vendor = random.choice(VENDORS)
        buyer = random.choice(BUYERS)
        po_num = f"PO-{random.randint(10000, 99999)}"
        date_po = datetime.date.today() - datetime.timedelta(days=random.randint(10, 60))
        tax_rate = TAX_RATES.get(vendor['country'], DEFAULT_TAX_RATE)

        # Select Items - ensure unique item descriptions per document,
        # using this vendor's exclusive catalog (vendor['items']).
        num_items = random.randint(1, 4)
        total_po_cost = 0
        selected_items = []

        vendor_items = vendor.get("items", [])
        chosen_templates = random.sample(vendor_items, k=min(num_items, len(vendor_items))) if vendor_items else []

        for item_tmpl in chosen_templates:
            qty = random.randint(1, 10)
            price = random.randint(*item_tmpl["price_range"])
            line_total = qty * price
            total_po_cost += line_total

            item_currency = item_tmpl.get("currency", vendor["currency"])

            selected_items.append({
                "sku": item_tmpl.get("sku", ""),
                "desc": item_tmpl["desc"],
                "qty": qty,
                "unit_price": price,
                "total": line_total,
                "currency": item_currency,
                "tax_rate": tax_rate,
            })

        # --- GENERATE PURCHASE ORDER ---
        po_context = {
            "po_num": po_num,
            "date": date_po,
            "currency": vendor['currency'],
            "vendor": vendor,
            "buyer": buyer,
            "items": selected_items,
            "subtotal": total_po_cost,
            "tax": total_po_cost * tax_rate,
            "tax_rate": tax_rate,
            "grand_total": total_po_cost * (1 + tax_rate),
        }
        generate_pdf(f"{OUTPUT_DIR}/incoming/{po_num}.pdf", po_context, "PO")

        # --- GENERATE GRN ---
        is_partial = random.random() < 0.10
        grn_date = date_po + datetime.timedelta(days=random.randint(2, 10))

        grn_items = []
        for item in selected_items:
            rec_qty = item['qty'] - 1 if (is_partial and item['qty'] > 1) else item['qty']
            status = 'Accepted' if rec_qty == item['qty'] else 'Partial / Damaged'
            grn_items.append({
                "sku": item.get('sku', ''),
                "desc": item['desc'],
                "qty": rec_qty,
                "status": status,
            })

        grn_context = {
            "grn_num": f"GR-{po_num[3:]}",
            "date": grn_date,
            "ref_po": po_num,
            "vendor": vendor,
            "buyer": buyer,
            "items": grn_items,
        }
        generate_pdf(f"{OUTPUT_DIR}/incoming/GRN-{po_num}.pdf", grn_context, "GRN")

        # --- GENERATE INVOICE ---
        invoice_num = f"INV-{random.randint(100000, 999999)}"
        invoice_date = date_po + datetime.timedelta(days=random.randint(5, 15))

        chaos_type = "NONE"
        if random.random() < CHAOS_RATE:
            chaos_type = random.choice(["PRICE_HIKE", "GHOST_PO", "CURRENCY_ERROR"])

        inv_items = selected_items.copy()
        inv_subtotal = total_po_cost
        inv_po_ref = po_num
        inv_currency = vendor['currency']
        chaos_note = ""

        if chaos_type == "PRICE_HIKE":
            markup = random.randint(100, 500)
            inv_subtotal += markup
            chaos_note = f"Includes unapproved Service Fee: {markup}"
            inv_items.append({
                "sku": "",
                "desc": "Expedited Shipping Fee",
                "qty": 1,
                "unit_price": markup,
                "total": markup,
                "currency": vendor['currency'],
            })

        elif chaos_type == "GHOST_PO":
            inv_po_ref = f"PO-{random.randint(10000, 99999)}"
            chaos_note = "System Ref Error: Unknown PO"

        elif chaos_type == "CURRENCY_ERROR":
            inv_currency = "USD"
            chaos_note = "Billing Error: Wrong Currency"

        tax = inv_subtotal * tax_rate

        buyer_country = buyer.get('country')
        buyer_currency = buyer.get('currency')
        vendor_country = vendor.get('country')

        apply_fx = buyer_country != vendor_country

        inv_context = {
            "inv_num": invoice_num,
            "date": invoice_date,
            "ref_po": inv_po_ref,
            "vendor": vendor,
            "buyer": buyer,
            "currency": inv_currency,
            "items": inv_items,
            "subtotal": inv_subtotal,
            "tax": tax,
            "tax_rate": tax_rate,
            "grand_total": inv_subtotal + tax,
            "buyer_country": buyer_country,
            "buyer_currency": buyer_currency,
            "note": chaos_note,
        }

        if apply_fx:
            vendor_to_usd = FX_RATES_TO_HOME.get(vendor['currency'], 1.0)
            buyer_to_usd = FX_RATES_TO_HOME.get(buyer_currency, 1.0)
            fx_rate = vendor_to_usd / buyer_to_usd if buyer_to_usd else 1.0
            subtotal_home = inv_subtotal * fx_rate
            tax_home = tax * fx_rate
            grand_total_home = (inv_subtotal + tax) * fx_rate
            inv_context.update({
                "home_currency": buyer_currency,
                "fx_rate": fx_rate,
                "subtotal_home": subtotal_home,
                "tax_home": tax_home,
                "grand_total_home": grand_total_home,
            })

        generate_pdf(f"{OUTPUT_DIR}/incoming/{invoice_num}.pdf", inv_context, "INV")

    print(f"Done! Created data in '{OUTPUT_DIR}'")

# ============================================================
# ENTRY POINT
# ============================================================

if __name__ == "__main__":
    generate_dataset()
