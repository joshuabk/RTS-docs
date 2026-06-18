"""Generate a professional PDF of a return-to-service report using ReportLab."""
from io import BytesIO

from django.utils import timezone
from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import (
    HRFlowable, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle,
)



INK = colors.HexColor("#16302c")
PETROL = colors.HexColor("#0e5c57")
MUTED = colors.HexColor("#5b6b67")
LINE = colors.HexColor("#d4ddda")
PAPER = colors.HexColor("#f3f6f4")


def _fmt(dt):
    if not dt:
        return "\u2014"
    if timezone.is_aware(dt):
        dt = timezone.localtime(dt)
    return dt.strftime("%d %b %Y, %H:%M")


def build_report_pdf(report):
    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer, pagesize=letter,
        topMargin=0.7 * inch, bottomMargin=0.7 * inch,
        leftMargin=0.75 * inch, rightMargin=0.75 * inch,
        title=f"{report.reference} Return to Service",
    )
    styles = getSampleStyleSheet()
    h_title = ParagraphStyle(
        "title", parent=styles["Title"], textColor=INK,
        fontSize=18, spaceAfter=2, alignment=TA_LEFT,
    )
    h_sub = ParagraphStyle(
        "sub", parent=styles["Normal"], textColor=MUTED, fontSize=9.5,
        fontName="Courier", spaceAfter=0,
    )
    label = ParagraphStyle(
        "label", parent=styles["Normal"], textColor=MUTED, fontSize=8,
        fontName="Helvetica-Bold", spaceAfter=2, leading=10,
    )
    value = ParagraphStyle(
        "value", parent=styles["Normal"], textColor=INK, fontSize=10.5,
        leading=14, spaceAfter=0,
    )
    section = ParagraphStyle(
        "section", parent=styles["Normal"], textColor=PETROL, fontSize=11,
        fontName="Helvetica-Bold", spaceBefore=14, spaceAfter=6,
    )
    mono = ParagraphStyle(
        "mono", parent=value, fontName="Courier", fontSize=10,
    )

    story = []

    # Header band
    status_label = report.get_status_display().upper()
    header_tbl = Table(
        [[
            Paragraph("RETURN-TO-SERVICE REPORT", h_title),
            Paragraph(status_label, ParagraphStyle(
                "status", parent=value, alignment=2, fontName="Helvetica-Bold",
                textColor=(PETROL if report.is_returned else MUTED), fontSize=11,
            )),
        ]],
        colWidths=[4.6 * inch, 2.4 * inch],
    )
    header_tbl.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 0),
    ]))
    story.append(header_tbl)
    story.append(Paragraph(report.reference, h_sub))
    story.append(Spacer(1, 6))
    story.append(HRFlowable(width="100%", thickness=1.4, color=PETROL))
    story.append(Spacer(1, 4))

    def kv_grid(rows):
        data = []
        for left, right in rows:
            data.append([
                Paragraph(left[0], label), Paragraph(left[1] or "\u2014", left[2]),
                Paragraph(right[0], label) if right else "",
                Paragraph(right[1] or "\u2014", right[2]) if right else "",
            ])
        # Stack label above value: rebuild as 2-col of stacked cells instead.
        return data

    def pair_table(items):
        """items: list of (label, value, style). Render two columns."""
        cells = []
        row = []
        for lab, val, sty in items:
            block = [Paragraph(lab, label), Paragraph(val or "\u2014", sty)]
            inner = Table([[b] for b in block], colWidths=[3.1 * inch])
            inner.setStyle(TableStyle([
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                ("TOPPADDING", (0, 0), (-1, -1), 1),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 1),
            ]))
            row.append(inner)
            if len(row) == 2:
                cells.append(row)
                row = []
        if row:
            row.append("")
            cells.append(row)
        t = Table(cells, colWidths=[3.35 * inch, 3.35 * inch])
        t.setStyle(TableStyle([
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("LEFTPADDING", (0, 0), (-1, -1), 0),
            ("RIGHTPADDING", (0, 0), (-1, -1), 0),
            ("TOPPADDING", (0, 0), (-1, -1), 6),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ]))
        return t

    m = report.machine
    story.append(Paragraph("Machine &amp; department", section))
    story.append(pair_table([
        ("MACHINE", m.name, value),
        ("DEPARTMENT", m.department.name, value),
        ("MACHINE TYPE", m.get_machine_type_display(), value),
        ("LOCATION", m.department.location, value),
        ("MANUFACTURER / MODEL", " ".join(x for x in [m.manufacturer, m.model] if x), value),
        ("SERIAL NUMBER", m.serial_number, mono),
    ]))

    story.append(HRFlowable(width="100%", thickness=0.6, color=LINE))
    story.append(Paragraph("Outage &amp; work", section))
    story.append(pair_table([
        ("OUTAGE START", _fmt(report.outage_start), mono),
        ("WORK COMPLETED", _fmt(report.work_completed_at), mono),
        ("WORK PERFORMED BY", report.performed_by, value),
        ("VENDOR DOCUMENTATION", report.vendor_doc_url, mono),
    ]))
    story.append(Paragraph("WORK PERFORMED", label))
    story.append(Paragraph((report.work_performed or "\u2014").replace("\n", "<br/>"), value))

    story.append(Spacer(1, 6))
    story.append(HRFlowable(width="100%", thickness=0.6, color=LINE))
    story.append(Paragraph("Physics evaluation", section))
    story.append(pair_table([
        ("STATUS", report.get_physics_status_display(), value),
        ("PHYSICIST", report.physicist, value),
    ]))
    story.append(Paragraph("EVALUATION PERFORMED", label))
    story.append(Paragraph(
        (report.physics_evaluation or "\u2014").replace("\n", "<br/>"), value))

    story.append(Spacer(1, 10))
    story.append(HRFlowable(width="100%", thickness=0.6, color=LINE))
    story.append(Paragraph("Approval", section))
    story.append(pair_table([
        ("RETURN TO SERVICE APPROVED BY", report.approved_by, value),
        ("APPROVAL DATE", _fmt(report.approval_date), mono),
    ]))

    story.append(Spacer(1, 22))
    story.append(HRFlowable(width="100%", thickness=0.6, color=LINE))
    footer = ParagraphStyle(
        "footer", parent=styles["Normal"], textColor=MUTED, fontSize=8,
        fontName="Courier",
    )
    story.append(Spacer(1, 4))
    story.append(Paragraph(
        f"{report.reference} &nbsp;|&nbsp; generated {_fmt(timezone.now())} "
        f"&nbsp;|&nbsp; created by {report.created_by or 'system'}", footer))

    doc.build(story)
    buffer.seek(0)
    return buffer
