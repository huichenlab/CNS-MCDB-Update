from __future__ import annotations

import argparse
import json
import re
import unicodedata
from pathlib import Path
from typing import Any, Iterable
from xml.sax.saxutils import escape, quoteattr

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import letter, landscape
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    BaseDocTemplate,
    Frame,
    HRFlowable,
    PageBreak,
    PageTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
)


PALETTE = {
    "Science": colors.HexColor("#A51935"),
    "Nature": colors.HexColor("#16697A"),
    "Cell": colors.HexColor("#C75B12"),
}
NAVY = colors.HexColor("#17324D")
SLATE = colors.HexColor("#526273")
PALE = colors.HexColor("#F3F6F8")
GOLD = colors.HexColor("#EAA43A")


def _font_name() -> str:
    candidates = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/local/share/fonts/DejaVuSans.ttf",
    ]
    for candidate in candidates:
        if Path(candidate).exists():
            pdfmetrics.registerFont(TTFont("RadarSans", candidate))
            return "RadarSans"
    return "Helvetica"


FONT = _font_name()


REPLACEMENTS = {
    "\u2010": "-", "\u2011": "-", "\u2012": "-", "\u2013": "-", "\u2014": "-", "\u2212": "-",
    "\u03b1": "alpha", "\u03b2": "beta", "\u03b3": "gamma", "\u03b4": "delta", "\u03b5": "epsilon",
    "\u03ba": "kappa", "\u03bb": "lambda", "\u03bc": "micro", "\u03c3": "sigma", "\u03c9": "omega",
    "\u0394": "Delta", "\u2265": ">=", "\u2264": "<=", "\u2192": "->", "\u00d7": "x",
}


def clean(value: Any) -> str:
    text = str(value or "")
    for source, target in REPLACEMENTS.items():
        text = text.replace(source, target)
    text = unicodedata.normalize("NFKC", text)
    return re.sub(r"\s+", " ", text).strip()


def paragraph(text: Any, style: ParagraphStyle) -> Paragraph:
    return Paragraph(escape(clean(text)), style)


def linked(label: str, url: str, style: ParagraphStyle) -> Paragraph:
    safe_label = escape(clean(label))
    safe_url = quoteattr(clean(url))
    return Paragraph(f"<link href={safe_url} color='#A51935'>{safe_label}</link>", style)


def bullets(values: Iterable[Any], style: ParagraphStyle) -> list[Any]:
    result: list[Any] = []
    for value in values or []:
        result.append(Paragraph(f"<bullet>&bull;</bullet>{escape(clean(value))}", style))
    return result


def _styles() -> dict[str, ParagraphStyle]:
    base = getSampleStyleSheet()
    return {
        "cover": ParagraphStyle("cover", parent=base["Title"], fontName=FONT, fontSize=28, leading=32, textColor=NAVY, alignment=TA_LEFT, spaceAfter=12),
        "subtitle": ParagraphStyle("subtitle", parent=base["Normal"], fontName=FONT, fontSize=13, leading=17, textColor=SLATE, spaceAfter=10),
        "title": ParagraphStyle("title", parent=base["Heading1"], fontName=FONT, fontSize=18, leading=22, textColor=NAVY, spaceAfter=8),
        "h2": ParagraphStyle("h2", parent=base["Heading2"], fontName=FONT, fontSize=11.5, leading=14, textColor=NAVY, spaceBefore=8, spaceAfter=4),
        "h3": ParagraphStyle("h3", parent=base["Heading3"], fontName=FONT, fontSize=9.5, leading=12, textColor=colors.HexColor("#8F1838"), spaceBefore=6, spaceAfter=3),
        "body": ParagraphStyle("body", parent=base["BodyText"], fontName=FONT, fontSize=8.2, leading=10.7, textColor=NAVY, spaceAfter=4),
        "small": ParagraphStyle("small", parent=base["BodyText"], fontName=FONT, fontSize=7.1, leading=9.2, textColor=SLATE, spaceAfter=3),
        "bullet": ParagraphStyle("bullet", parent=base["BodyText"], fontName=FONT, fontSize=7.8, leading=10, leftIndent=11, firstLineIndent=-7, bulletIndent=2, textColor=NAVY, spaceAfter=2),
        "tag": ParagraphStyle("tag", parent=base["BodyText"], fontName=FONT, fontSize=7.4, leading=9, textColor=colors.white, alignment=TA_CENTER),
    }


def render_report(report: dict[str, Any], output_path: str | Path) -> Path:
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    issue = report["issue"]
    accent = PALETTE.get(issue.get("journal"), colors.HexColor("#A51935"))
    styles = _styles()

    doc = BaseDocTemplate(
        str(output), pagesize=landscape(letter),
        leftMargin=0.52 * inch, rightMargin=0.52 * inch,
        topMargin=0.52 * inch, bottomMargin=0.45 * inch,
        title=f"CNS MCDB Update - {issue.get('journal')} {issue.get('volume')}({issue.get('issue')})",
        author="CNS MCDB Update",
    )
    frame = Frame(doc.leftMargin, doc.bottomMargin, doc.width, doc.height, id="main")

    def decorate(canvas, current_doc):
        canvas.saveState()
        canvas.setStrokeColor(colors.HexColor("#CBD5DF"))
        canvas.line(doc.leftMargin, 0.34 * inch, landscape(letter)[0] - doc.rightMargin, 0.34 * inch)
        canvas.setFont(FONT, 6.8)
        canvas.setFillColor(SLATE)
        footer = f"CNS MCDB Update | {clean(issue.get('journal'))} {clean(issue.get('volume'))}({clean(issue.get('issue'))}) | Deterministic public-evidence synthesis - verify before grant use"
        canvas.drawString(doc.leftMargin, 0.20 * inch, footer)
        canvas.drawRightString(landscape(letter)[0] - doc.rightMargin, 0.20 * inch, str(current_doc.page))
        canvas.restoreState()

    doc.addPageTemplates([PageTemplate(id="radar", frames=[frame], onPage=decorate)])
    story: list[Any] = []

    story += [
        Spacer(1, 0.18 * inch),
        paragraph("CNS MCDB UPDATE", styles["subtitle"]),
        paragraph(f"{issue.get('journal')} | Volume {issue.get('volume')} | Issue {issue.get('issue')}", styles["cover"]),
        paragraph(f"Issue date: {issue.get('issue_date')} | Retrieved: {issue.get('retrieved_at')} | {len(report.get('papers') or [])} relevant primary-research papers", styles["subtitle"]),
        HRFlowable(width="100%", thickness=4, color=accent, spaceBefore=4, spaceAfter=12),
        paragraph("Evidence discipline", styles["h2"]),
        paragraph("Paper-supported findings, published enabling evidence, cross-species inference, speculative hypotheses, and proposed pilot experiments are labeled separately. Access notes state when only an abstract or limited preview was available.", styles["body"]),
        paragraph("Screening notes", styles["h2"]),
        *bullets(report.get("screening_notes") or [], styles["bullet"]),
        paragraph("Official issue", styles["h2"]),
        linked(issue.get("canonical_issue_url", "Official issue page"), issue.get("canonical_issue_url", ""), styles["body"]),
        paragraph("Why Xenopus now", styles["h2"]),
        paragraph((report.get("cross_paper_synthesis") or {}).get("why_xenopus_now", ""), styles["body"]),
    ]

    for paper_index, paper in enumerate(report.get("papers") or [], start=1):
        story += [
            PageBreak(),
            paragraph(f"{paper.get('journal')} | PAPER {paper_index} OF {len(report['papers'])}", styles["subtitle"]),
            paragraph(paper.get("title"), styles["title"]),
            paragraph(paper.get("authors"), styles["small"]),
        ]
        metadata = [
            paragraph(f"{paper.get('article_type')} | {paper.get('journal')} {paper.get('volume')}({paper.get('issue')}) | {paper.get('publication_date')}", styles["small"]),
            linked(f"DOI {paper.get('doi')}", paper.get("canonical_url", ""), styles["small"]),
            paragraph(f"Access: {paper.get('access_note')} | Evidence status: {paper.get('source_status')}", styles["small"]),
        ]
        story.append(Table([[metadata]], colWidths=[doc.width], style=TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), PALE), ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#CDD8E3")),
            ("LEFTPADDING", (0, 0), (-1, -1), 7), ("RIGHTPADDING", (0, 0), (-1, -1), 7),
            ("TOPPADDING", (0, 0), (-1, -1), 6), ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ])))
        summary_cells = [
            [paragraph("MAIN DISCOVERY", styles["h3"]), paragraph(paper.get("main_discovery"), styles["body"])],
            [paragraph("WHY IT MATTERS", styles["h3"]), paragraph(paper.get("importance_implication"), styles["body"])],
            [paragraph("MAIN / NEW METHODS", styles["h3"]), bullets(paper.get("methods") or [], styles["bullet"])],
            [paragraph("KEY EVIDENCE", styles["h3"]), bullets(paper.get("key_evidence") or [], styles["bullet"])],
            [paragraph("LIMITATIONS", styles["h3"]), bullets(paper.get("limitations") or [], styles["bullet"])],
        ]
        story.append(Table(summary_cells, colWidths=[1.55 * inch, doc.width - 1.55 * inch], style=TableStyle([
            ("VALIGN", (0, 0), (-1, -1), "TOP"), ("GRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#D7E0E8")),
            ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#F8ECEF")),
            ("LEFTPADDING", (0, 0), (-1, -1), 7), ("RIGHTPADDING", (0, 0), (-1, -1), 7),
            ("TOPPADDING", (0, 0), (-1, -1), 4), ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ]), repeatRows=0))

        for idea_index, idea in enumerate(paper.get("grant_ideas") or [], start=1):
            story += [
                PageBreak(),
                paragraph(f"SPECIFIC GRANT IDEA {idea_index} | PAPER {paper_index}", styles["subtitle"]),
                paragraph(idea.get("working_title"), styles["title"]),
                HRFlowable(width="100%", thickness=3, color=GOLD, spaceAfter=8),
            ]
            fields = [
                ("IMPORTANCE / SIGNIFICANCE", idea.get("importance")),
                ("KNOWLEDGE GAP", idea.get("knowledge_gap")),
                ("RATIONALE AND XENOPUS ADVANTAGE", idea.get("rationale_xenopus_advantage")),
                ("CENTRAL HYPOTHESIS", idea.get("central_hypothesis")),
                ("EXPERIMENTAL DESIGN", idea.get("experimental_design")),
                ("EXPECTED RESULTS AND INTERPRETATIONS", idea.get("expected_results_interpretations")),
                ("POTENTIAL PITFALLS", idea.get("potential_pitfalls")),
                ("ALTERNATIVE STRATEGIES", idea.get("alternative_strategies")),
                ("PUBLISHED ENABLING EVIDENCE AND PROPOSED PRELIMINARY-DATA PLAN", idea.get("preliminary_evidence_plan")),
            ]
            for label, value in fields:
                story.append(paragraph(label, styles["h3"]))
                if isinstance(value, list):
                    story.extend(bullets(value, styles["bullet"]))
                else:
                    story.append(paragraph(value, styles["body"]))
            ratings = [[
                paragraph(f"NOVELTY\n{idea.get('novelty')}", styles["small"]),
                paragraph(f"FEASIBILITY\n{idea.get('feasibility')}", styles["small"]),
                paragraph(f"RISK\n{idea.get('risk')}", styles["small"]),
            ]]
            story.append(Table(ratings, colWidths=[doc.width / 3] * 3, style=TableStyle([
                ("BACKGROUND", (0, 0), (-1, -1), PALE), ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#CCD6E0")),
                ("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 7),
                ("RIGHTPADDING", (0, 0), (-1, -1), 7), ("TOPPADDING", (0, 0), (-1, -1), 6), ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
            ])))
            story += [paragraph("GRANT FIT", styles["h3"]), paragraph(idea.get("grant_fit"), styles["body"]), paragraph("STRONGEST REVIEWER-FACING PREMISE", styles["h3"]), paragraph(idea.get("reviewer_premise"), styles["body"])]
            sources = idea.get("supporting_sources") or []
            if sources:
                story.append(paragraph("SUPPORTING SOURCES", styles["h3"]))
                for source in sources:
                    label = f"{source.get('evidence_type')}: {source.get('citation')} {source.get('doi_or_pmid')}"
                    url = source.get("url") or ""
                    story.append(linked(label, url, styles["small"]) if url else paragraph(label, styles["small"]))

    synthesis = report.get("cross_paper_synthesis") or {}
    story += [PageBreak(), paragraph("CROSS-PAPER SYNTHESIS", styles["title"]), HRFlowable(width="100%", thickness=4, color=accent, spaceAfter=8)]
    for label, values in (("RECURRING MECHANISMS", synthesis.get("recurring_mechanisms")), ("METHODOLOGICAL TRENDS", synthesis.get("methodological_trends"))):
        story.append(paragraph(label, styles["h2"]))
        story.extend(bullets(values or [], styles["bullet"]))
    story.append(paragraph("RANKED XENOPUS OPPORTUNITIES", styles["h2"]))
    for opportunity in synthesis.get("ranked_opportunities") or []:
        story.append(paragraph(f"#{opportunity.get('rank')} {opportunity.get('title')}", styles["h3"]))
        compact = " | ".join(f"{key.replace('_', ' ').title()}: {clean(opportunity.get(key))}" for key in ("significance", "novelty", "mechanistic_clarity", "preliminary_support", "xenopus_advantage", "feasibility", "follow_on_aims"))
        story.append(paragraph(compact, styles["body"]))
    story += [
        paragraph("COHERENT MULTI-AIM PROPOSAL", styles["h2"]), paragraph(synthesis.get("coherent_multi_aim_proposal"), styles["body"]),
        paragraph("INDEPENDENT PILOTS", styles["h2"]), *bullets(synthesis.get("independent_pilots") or [], styles["bullet"]),
        paragraph("SOURCE / METHOD NOTE", styles["h2"]), paragraph(report.get("source_method_note"), styles["small"]),
    ]
    doc.build(story)
    return output


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("report_json")
    parser.add_argument("output_pdf")
    args = parser.parse_args()
    render_report(json.loads(Path(args.report_json).read_text()), args.output_pdf)


if __name__ == "__main__":
    main()
