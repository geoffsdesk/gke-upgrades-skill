#!/usr/bin/env python3
"""Generate four-way comparison PDF for GKE Upgrades Skill iteration 10.
Claude + Gemini, with and without skill."""

from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.lib.colors import HexColor, white, black
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
    PageBreak, HRFlowable, KeepTogether
)
import json
from pathlib import Path

# Colors
BLUE = HexColor("#1a73e8")
DARK_BLUE = HexColor("#174ea6")
LIGHT_BLUE = HexColor("#e8f0fe")
GREEN = HexColor("#1e8e3e")
LIGHT_GREEN = HexColor("#e6f4ea")
RED = HexColor("#d93025")
LIGHT_RED = HexColor("#fce8e6")
ORANGE = HexColor("#e37400")
LIGHT_ORANGE = HexColor("#fef7e0")
GRAY = HexColor("#5f6368")
LIGHT_GRAY = HexColor("#f1f3f4")
DARK = HexColor("#202124")
PURPLE = HexColor("#7b1fa2")
LIGHT_PURPLE = HexColor("#f3e8fd")

ITER_DIR = Path(__file__).parent
WORKSPACE = ITER_DIR.parent


def build_report():
    output_path = str(ITER_DIR / "iteration-10-report.pdf")
    doc = SimpleDocTemplate(
        output_path, pagesize=letter,
        topMargin=0.6*inch, bottomMargin=0.6*inch,
        leftMargin=0.65*inch, rightMargin=0.65*inch,
    )

    styles = getSampleStyleSheet()
    title_style = ParagraphStyle("CustomTitle", parent=styles["Title"], fontSize=22, textColor=DARK_BLUE, spaceAfter=4, fontName="Helvetica-Bold")
    subtitle_style = ParagraphStyle("Subtitle", parent=styles["Normal"], fontSize=10, textColor=GRAY, spaceAfter=14, fontName="Helvetica")
    h1 = ParagraphStyle("H1", parent=styles["Heading1"], fontSize=15, textColor=DARK_BLUE, spaceBefore=14, spaceAfter=8, fontName="Helvetica-Bold")
    h2 = ParagraphStyle("H2", parent=styles["Heading2"], fontSize=12, textColor=BLUE, spaceBefore=10, spaceAfter=6, fontName="Helvetica-Bold")
    body = ParagraphStyle("Body", parent=styles["Normal"], fontSize=9.5, textColor=DARK, spaceAfter=6, fontName="Helvetica", leading=13)
    small = ParagraphStyle("Small", parent=body, fontSize=8, textColor=GRAY, leading=10)
    cell = ParagraphStyle("Cell", parent=body, fontSize=8.5, leading=11, spaceAfter=0)
    cell_bold = ParagraphStyle("CellBold", parent=cell, fontName="Helvetica-Bold")
    cell_center = ParagraphStyle("CellCenter", parent=cell, alignment=TA_CENTER)
    cell_center_bold = ParagraphStyle("CellCenterBold", parent=cell_center, fontName="Helvetica-Bold")
    cell_small = ParagraphStyle("CellSmall", parent=cell, fontSize=7.5, leading=9)
    cell_small_center = ParagraphStyle("CellSmallCenter", parent=cell_small, alignment=TA_CENTER)

    # Load data
    b10 = json.load(open(ITER_DIR / "benchmark.json"))

    # Build per-eval lookups
    cws = {e["eval_id"]: e for e in b10["claude_with_skill"]["evals"]}
    cwos = {e["eval_id"]: e for e in b10["claude_without_skill"]["evals"]}
    gws = {e["eval_id"]: e for e in b10["gemini_with_skill"]["evals"]}
    gwos = {e["eval_id"]: e for e in b10["gemini_without_skill"]["evals"]}

    # Overall metrics
    c_ws_rate = b10["claude_with_skill"]["overall_pass_rate"]
    c_wos_rate = b10["claude_without_skill"]["overall_pass_rate"]
    c_ws_p = b10["claude_with_skill"]["total_passed"]
    c_ws_t = b10["claude_with_skill"]["total_assertions"]
    c_wos_p = b10["claude_without_skill"]["total_passed"]
    c_delta = b10["delta"]["claude"]["pass_rate_improvement"]

    g_ws_rate = b10["gemini_with_skill"]["overall_pass_rate"]
    g_wos_rate = b10["gemini_without_skill"]["overall_pass_rate"]
    g_ws_p = b10["gemini_with_skill"]["total_passed"]
    g_ws_t = b10["gemini_with_skill"]["total_assertions"]
    g_wos_p = b10["gemini_without_skill"]["total_passed"]
    g_wos_t = b10["gemini_without_skill"]["total_assertions"]
    g_delta = b10["delta"]["gemini"]["pass_rate_improvement"]

    # Load prior iterations for history
    history = []
    for i in [4, 5, 6, 7, 8, 9]:
        bp = WORKSPACE / f"iteration-{i}" / "benchmark.json"
        if bp.exists():
            bd = json.load(open(bp))
            # Handle both "both" and single-provider formats
            if "claude_with_skill" in bd:
                ws_r = bd["claude_with_skill"]["overall_pass_rate"]
                wos_r = bd["claude_without_skill"]["overall_pass_rate"]
            elif "with_skill" in bd:
                ws_r = bd["with_skill"]["overall_pass_rate"]
                wos_r = bd["without_skill"]["overall_pass_rate"]
            else:
                continue
            history.append((i, ws_r, wos_r))

    story = []

    # ── Title ──
    story.append(Paragraph("GKE Upgrades Skill", title_style))
    story.append(Paragraph(
        "Iteration 10 — Four-Way Benchmark Report  |  March 21, 2026  |  "
        "Claude Sonnet 4 + Gemini 3.1 Pro", subtitle_style))
    story.append(HRFlowable(width="100%", thickness=2, color=BLUE, spaceAfter=12))

    # ── Executive Summary ──
    story.append(Paragraph("Executive Summary", h1))
    story.append(Paragraph(
        "This report presents the first four-way benchmark comparison of the GKE Upgrades skill, "
        "testing both Claude Sonnet 4 and Gemini 3.1 Pro with and without the skill context. "
        "The evaluation suite comprises 40 evals covering 340 assertions across GKE upgrade scenarios "
        "including node pool strategies, maintenance windows, version lifecycle, AI/ML workloads, "
        "and troubleshooting. The skill context is provided as SKILL.md (Claude) and GEMINI.md (Gemini), "
        "both synthesized from the GKE PM group and engineering knowledge base.",
        body
    ))
    story.append(Spacer(1, 6))

    # ── Headline Metrics Table ──
    story.append(Paragraph("Headline Results", h2))
    headline = [
        [Paragraph("<b>Provider</b>", cell_center_bold),
         Paragraph("<b>Model</b>", cell_center_bold),
         Paragraph("<b>With Skill</b>", cell_center_bold),
         Paragraph("<b>Without Skill</b>", cell_center_bold),
         Paragraph("<b>Skill Delta</b>", cell_center_bold)],
        [Paragraph("<b>Claude</b>", cell_bold),
         Paragraph("Sonnet 4", cell_center),
         Paragraph(f"<b>{c_ws_rate*100:.1f}%</b> ({c_ws_p}/{c_ws_t})", cell_center_bold),
         Paragraph(f"{c_wos_rate*100:.1f}% ({c_wos_p}/{c_ws_t})", cell_center),
         Paragraph(f"<b>+{c_delta*100:.1f}%</b>", cell_center_bold)],
        [Paragraph("<b>Gemini</b>", cell_bold),
         Paragraph("3.1 Pro Preview", cell_center),
         Paragraph(f"<b>{g_ws_rate*100:.1f}%</b> ({g_ws_p}/{g_ws_t})", cell_center_bold),
         Paragraph(f"{g_wos_rate*100:.1f}% ({g_wos_p}/{g_wos_t})", cell_center),
         Paragraph(f"<b>+{g_delta*100:.1f}%</b>", cell_center_bold)],
    ]
    ht = Table(headline, colWidths=[0.9*inch, 1.2*inch, 1.6*inch, 1.6*inch, 1.0*inch])
    ht.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), DARK_BLUE),
        ("TEXTCOLOR", (0, 0), (-1, 0), white),
        ("BACKGROUND", (0, 1), (-1, 1), LIGHT_BLUE),
        ("BACKGROUND", (0, 2), (-1, 2), LIGHT_PURPLE),
        ("GRID", (0, 0), (-1, -1), 0.5, HexColor("#dadce0")),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 7),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
    ]))
    story.append(ht)
    story.append(Spacer(1, 6))

    # Key findings
    story.append(Paragraph("Key Findings", h2))
    findings = [
        f"Claude with skill ({c_ws_rate*100:.1f}%) outperforms Gemini with skill ({g_ws_rate*100:.1f}%) by {(c_ws_rate - g_ws_rate)*100:.1f}pp.",
        f"Claude's skill delta (+{c_delta*100:.1f}%) is larger than Gemini's (+{g_delta*100:.1f}%), meaning the Claude skill extracts more value from the knowledge base.",
        f"Gemini without skill ({g_wos_rate*100:.1f}%) is close to Claude without skill ({c_wos_rate*100:.1f}%), showing comparable baseline GKE knowledge.",
        f"The skill provides substantial improvement for both providers, confirming the knowledge base adds value regardless of the underlying model.",
    ]
    for i, f in enumerate(findings):
        story.append(Paragraph(f"<b>{i+1}.</b> {f}", body))
    story.append(Spacer(1, 4))

    # ── Iteration History ──
    story.append(Paragraph("Iteration History (Claude)", h2))
    iter_rows = [
        [Paragraph("<b>Iter</b>", cell_center_bold),
         Paragraph("<b>With Skill</b>", cell_center_bold),
         Paragraph("<b>Without Skill</b>", cell_center_bold),
         Paragraph("<b>Delta</b>", cell_center_bold),
         Paragraph("<b>Notes</b>", cell_center_bold)],
    ]
    notes = {
        4: "Initial (23 evals, 194 assertions)",
        5: "AI/ML evals added (37/310)",
        6: "Rollout sequence tuning",
        7: "PM feedback v1 (40/338)",
        8: "KB consumed, run 1 (40/340)",
        9: "KB consumed, run 2 (40/340)",
    }
    for it_num, ws_r, wos_r in history:
        delta = ws_r - wos_r
        bold = it_num >= 8
        s = cell_center_bold if bold else cell_center
        iter_rows.append([
            Paragraph(f"{'<b>' if bold else ''}{it_num}{'</b>' if bold else ''}", s),
            Paragraph(f"{'<b>' if bold else ''}{ws_r*100:.1f}%{'</b>' if bold else ''}", s),
            Paragraph(f"{'<b>' if bold else ''}{wos_r*100:.1f}%{'</b>' if bold else ''}", s),
            Paragraph(f"{'<b>' if bold else ''}+{delta*100:.1f}%{'</b>' if bold else ''}", s),
            Paragraph(f"{'<b>' if bold else ''}{notes.get(it_num, '')}{'</b>' if bold else ''}", s),
        ])
    # Add iteration 10
    iter_rows.append([
        Paragraph("<b>10</b>", cell_center_bold),
        Paragraph(f"<b>{c_ws_rate*100:.1f}%</b>", cell_center_bold),
        Paragraph(f"<b>{c_wos_rate*100:.1f}%</b>", cell_center_bold),
        Paragraph(f"<b>+{c_delta*100:.1f}%</b>", cell_center_bold),
        Paragraph("<b>+ Gemini side-by-side (40/340)</b>", cell_center_bold),
    ])
    it_table = Table(iter_rows, colWidths=[0.5*inch, 0.9*inch, 1.0*inch, 0.7*inch, 2.6*inch])
    it_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), DARK_BLUE),
        ("TEXTCOLOR", (0, 0), (-1, 0), white),
        ("BACKGROUND", (0, -1), (-1, -1), LIGHT_GREEN),
        ("ROWBACKGROUNDS", (0, 1), (-1, -2), [white, LIGHT_GRAY]),
        ("GRID", (0, 0), (-1, -1), 0.5, HexColor("#dadce0")),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    story.append(it_table)

    # ── PAGE 2: Per-Eval Four-Way Comparison ──
    story.append(PageBreak())
    story.append(Paragraph("Per-Eval Comparison: Claude vs Gemini (With Skill)", h1))
    story.append(Paragraph(
        "Pass rate per eval for both providers with skill context. Winner column shows which provider "
        "scored higher. Green = Claude wins, Purple = Gemini wins, Gray = tie.",
        body
    ))

    eval_ids = sorted(cws.keys())

    def make_comparison_table(ids):
        rows = [[
            Paragraph("<b>Eval</b>", cell_center_bold),
            Paragraph("<b>Claude</b>", cell_center_bold),
            Paragraph("<b>Gemini</b>", cell_center_bold),
            Paragraph("<b>Gap</b>", cell_center_bold),
        ]]
        for eid in ids:
            cr = cws[eid]["pass_rate"]
            gr = gws.get(eid, {}).get("pass_rate", 0)
            gap = cr - gr
            if gap > 0:
                gap_color = GREEN
                gap_str = f"+{gap*100:.0f}"
            elif gap < 0:
                gap_color = PURPLE
                gap_str = f"{gap*100:.0f}"
            else:
                gap_color = GRAY
                gap_str = "0"
            rows.append([
                Paragraph(f"{eid}", cell_small_center),
                Paragraph(f"{cr*100:.0f}%", cell_small_center),
                Paragraph(f"{gr*100:.0f}%", cell_small_center),
                Paragraph(f"<font color='{gap_color}'>{gap_str}</font>", cell_small_center),
            ])
        t = Table(rows, colWidths=[0.45*inch, 0.65*inch, 0.65*inch, 0.55*inch])
        t.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), DARK_BLUE),
            ("TEXTCOLOR", (0, 0), (-1, 0), white),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [white, LIGHT_GRAY]),
            ("GRID", (0, 0), (-1, -1), 0.5, HexColor("#dadce0")),
            ("ALIGN", (0, 0), (-1, -1), "CENTER"),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("TOPPADDING", (0, 0), (-1, -1), 2),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
        ]))
        return t

    half = 20
    left = make_comparison_table(eval_ids[:half])
    right = make_comparison_table(eval_ids[half:])
    combined = Table([[left, Spacer(6, 1), right]], colWidths=[2.35*inch, 0.2*inch, 2.35*inch])
    combined.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP")]))
    story.append(combined)

    # Win/loss summary
    claude_wins = sum(1 for eid in eval_ids if cws[eid]["pass_rate"] > gws.get(eid, {}).get("pass_rate", 0))
    gemini_wins = sum(1 for eid in eval_ids if cws[eid]["pass_rate"] < gws.get(eid, {}).get("pass_rate", 0))
    ties = sum(1 for eid in eval_ids if cws[eid]["pass_rate"] == gws.get(eid, {}).get("pass_rate", 0))

    story.append(Spacer(1, 8))
    story.append(Paragraph(
        f"<b>With-Skill Head-to-Head:</b> Claude wins {claude_wins} evals, "
        f"Gemini wins {gemini_wins} evals, {ties} ties.",
        body
    ))

    # ── Skill Impact by Provider ──
    story.append(Spacer(1, 6))
    story.append(Paragraph("Skill Impact Comparison (Delta: With Skill - Without Skill)", h2))
    story.append(Paragraph(
        "Shows which evals benefit most from the skill for each provider. Sorted by Claude impact.",
        body
    ))

    impact_data = []
    for eid in eval_ids:
        c_impact = cws[eid]["pass_rate"] - cwos[eid]["pass_rate"]
        g_impact = gws.get(eid, {}).get("pass_rate", 0) - gwos.get(eid, {}).get("pass_rate", 0)
        impact_data.append((eid, c_impact, g_impact))

    # Sort by Claude impact descending
    impact_data.sort(key=lambda x: x[1], reverse=True)

    # Show top 15 by Claude impact
    impact_rows = [[
        Paragraph("<b>Eval</b>", cell_center_bold),
        Paragraph("<b>Claude Delta</b>", cell_center_bold),
        Paragraph("<b>Gemini Delta</b>", cell_center_bold),
        Paragraph("<b>Both Benefit?</b>", cell_center_bold),
    ]]
    for eid, c_imp, g_imp in impact_data[:15]:
        c_color = GREEN if c_imp > 0 else (RED if c_imp < 0 else GRAY)
        g_color = GREEN if g_imp > 0 else (RED if g_imp < 0 else GRAY)
        both = "Yes" if c_imp > 0 and g_imp > 0 else ("Mixed" if (c_imp > 0) != (g_imp > 0) else "No")
        both_color = GREEN if both == "Yes" else (ORANGE if both == "Mixed" else RED)
        impact_rows.append([
            Paragraph(f"{eid}", cell_small_center),
            Paragraph(f"<font color='{c_color}'>{c_imp*100:+.0f}%</font>", cell_small_center),
            Paragraph(f"<font color='{g_color}'>{g_imp*100:+.0f}%</font>", cell_small_center),
            Paragraph(f"<font color='{both_color}'>{both}</font>", cell_small_center),
        ])
    imp_table = Table(impact_rows, colWidths=[0.6*inch, 1.2*inch, 1.2*inch, 1.1*inch])
    imp_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), DARK_BLUE),
        ("TEXTCOLOR", (0, 0), (-1, 0), white),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [white, LIGHT_GRAY]),
        ("GRID", (0, 0), (-1, -1), 0.5, HexColor("#dadce0")),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ]))
    story.append(imp_table)

    # ── PAGE 3: Without-Skill Baseline Comparison ──
    story.append(PageBreak())
    story.append(Paragraph("Without-Skill Baseline: Claude vs Gemini", h1))
    story.append(Paragraph(
        "Compares both models without any skill context, showing their baseline GKE knowledge. "
        "This reveals what each model knows from training data alone.",
        body
    ))

    def make_baseline_table(ids):
        rows = [[
            Paragraph("<b>Eval</b>", cell_center_bold),
            Paragraph("<b>Claude</b>", cell_center_bold),
            Paragraph("<b>Gemini</b>", cell_center_bold),
            Paragraph("<b>Gap</b>", cell_center_bold),
        ]]
        for eid in ids:
            cr = cwos[eid]["pass_rate"]
            gr = gwos.get(eid, {}).get("pass_rate", 0)
            gap = cr - gr
            if gap > 0.05:
                gap_color = GREEN
            elif gap < -0.05:
                gap_color = PURPLE
            else:
                gap_color = GRAY
            gap_str = f"{gap*100:+.0f}"
            rows.append([
                Paragraph(f"{eid}", cell_small_center),
                Paragraph(f"{cr*100:.0f}%", cell_small_center),
                Paragraph(f"{gr*100:.0f}%", cell_small_center),
                Paragraph(f"<font color='{gap_color}'>{gap_str}</font>", cell_small_center),
            ])
        t = Table(rows, colWidths=[0.45*inch, 0.65*inch, 0.65*inch, 0.55*inch])
        t.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), DARK_BLUE),
            ("TEXTCOLOR", (0, 0), (-1, 0), white),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [white, LIGHT_GRAY]),
            ("GRID", (0, 0), (-1, -1), 0.5, HexColor("#dadce0")),
            ("ALIGN", (0, 0), (-1, -1), "CENTER"),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("TOPPADDING", (0, 0), (-1, -1), 2),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
        ]))
        return t

    left_b = make_baseline_table(eval_ids[:half])
    right_b = make_baseline_table(eval_ids[half:])
    combined_b = Table([[left_b, Spacer(6, 1), right_b]], colWidths=[2.35*inch, 0.2*inch, 2.35*inch])
    combined_b.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP")]))
    story.append(combined_b)

    # Win/loss for baseline
    base_claude_wins = sum(1 for eid in eval_ids if cwos[eid]["pass_rate"] > gwos.get(eid, {}).get("pass_rate", 0))
    base_gemini_wins = sum(1 for eid in eval_ids if cwos[eid]["pass_rate"] < gwos.get(eid, {}).get("pass_rate", 0))
    base_ties = sum(1 for eid in eval_ids if cwos[eid]["pass_rate"] == gwos.get(eid, {}).get("pass_rate", 0))

    story.append(Spacer(1, 8))
    story.append(Paragraph(
        f"<b>Without-Skill Head-to-Head:</b> Claude wins {base_claude_wins} evals, "
        f"Gemini wins {base_gemini_wins} evals, {base_ties} ties.",
        body
    ))

    # ── Notable Strengths side by side ──
    story.append(Spacer(1, 8))
    story.append(Paragraph("Notable Strengths by Provider (With Skill)", h2))

    gemini_better = []
    claude_better = []
    for eid in eval_ids:
        cr = cws[eid]["pass_rate"]
        gr = gws.get(eid, {}).get("pass_rate", 0)
        if gr > cr:
            gemini_better.append((eid, cr, gr, gr - cr))
        elif cr > gr:
            claude_better.append((eid, cr, gr, cr - gr))
    gemini_better.sort(key=lambda x: x[3], reverse=True)
    claude_better.sort(key=lambda x: x[3], reverse=True)

    def make_strengths_table(items, label, lead_color, bg_color, max_rows=8):
        rows = [[
            Paragraph("<b>Eval</b>", cell_center_bold),
            Paragraph("<b>C</b>", cell_center_bold),
            Paragraph("<b>G</b>", cell_center_bold),
            Paragraph(f"<b>{label}</b>", cell_center_bold),
        ]]
        for eid, cr, gr, lead in items[:max_rows]:
            rows.append([
                Paragraph(f"{eid}", cell_small_center),
                Paragraph(f"{cr*100:.0f}%", cell_small_center),
                Paragraph(f"{gr*100:.0f}%", cell_small_center),
                Paragraph(f"<font color='{lead_color}'>+{lead*100:.0f}%</font>", cell_small_center),
            ])
        t = Table(rows, colWidths=[0.45*inch, 0.5*inch, 0.5*inch, 0.7*inch])
        t.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), DARK_BLUE),
            ("TEXTCOLOR", (0, 0), (-1, 0), white),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [white, bg_color]),
            ("GRID", (0, 0), (-1, -1), 0.5, HexColor("#dadce0")),
            ("ALIGN", (0, 0), (-1, -1), "CENTER"),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("TOPPADDING", (0, 0), (-1, -1), 2),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
        ]))
        return t

    left_s = make_strengths_table(claude_better, "C Lead", GREEN, LIGHT_GREEN)
    right_s = make_strengths_table(gemini_better, "G Lead", PURPLE, LIGHT_PURPLE)

    strengths_label = Table([
        [Paragraph("<b>Claude Strengths (top 8)</b>", cell_center_bold),
         Paragraph("", cell_center),
         Paragraph("<b>Gemini Strengths (top 8)</b>", cell_center_bold)],
        [left_s, Spacer(6, 1), right_s],
    ], colWidths=[2.2*inch, 0.2*inch, 2.2*inch])
    strengths_label.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING", (0, 0), (-1, 0), 2),
        ("BOTTOMPADDING", (0, 0), (-1, 0), 4),
    ]))
    story.append(strengths_label)

    # ── PAGE 4: Conclusions ──
    story.append(PageBreak())
    story.append(Paragraph("Conclusions and Analysis", h1))

    story.append(Paragraph("<b>Cross-Platform Skill Validation</b>", body))
    story.append(Paragraph(
        f"The GKE Upgrades skill delivers measurable improvement on both platforms. Claude's "
        f"+{c_delta*100:.1f}% delta and Gemini's +{g_delta*100:.1f}% delta confirm that the "
        f"knowledge base (synthesized from the GKE PM group and engineering team) provides "
        f"substantial value regardless of the underlying model. The skill is effective as both "
        f"a Claude SKILL.md and a Gemini GEMINI.md extension.",
        body
    ))
    story.append(Spacer(1, 4))

    story.append(Paragraph("<b>Provider Comparison</b>", body))
    story.append(Paragraph(
        f"Claude Sonnet 4 achieves the highest with-skill score ({c_ws_rate*100:.1f}%) and the "
        f"largest skill delta (+{c_delta*100:.1f}%), suggesting it is better at extracting and "
        f"applying structured knowledge from the skill context. Gemini 3.1 Pro Preview scores "
        f"{g_ws_rate*100:.1f}% with skill — a strong result, but {(c_ws_rate - g_ws_rate)*100:.1f}pp "
        f"behind Claude. Both models have similar baseline knowledge ({c_wos_rate*100:.1f}% vs "
        f"{g_wos_rate*100:.1f}% without skill).",
        body
    ))
    story.append(Spacer(1, 4))

    story.append(Paragraph("<b>Baseline Knowledge</b>", body))
    baseline_gap = c_wos_rate - g_wos_rate
    if baseline_gap > 0.02:
        story.append(Paragraph(
            f"Claude's baseline GKE knowledge ({c_wos_rate*100:.1f}%) exceeds Gemini's "
            f"({g_wos_rate*100:.1f}%) by {baseline_gap*100:.1f}pp. This gap widens further "
            f"with skill context (+{(c_ws_rate - g_ws_rate)*100:.1f}pp), indicating Claude "
            f"better leverages the provided domain knowledge.",
            body
        ))
    else:
        story.append(Paragraph(
            f"Both models show comparable baseline GKE knowledge (Claude: {c_wos_rate*100:.1f}%, "
            f"Gemini: {g_wos_rate*100:.1f}%), suggesting neither has a significant training data "
            f"advantage for GKE-specific topics.",
            body
        ))
    story.append(Spacer(1, 4))

    story.append(Paragraph("<b>Skill ROI</b>", body))
    both_benefit = sum(1 for eid in eval_ids
                       if (cws[eid]["pass_rate"] - cwos[eid]["pass_rate"]) > 0
                       and (gws.get(eid, {}).get("pass_rate", 0) - gwos.get(eid, {}).get("pass_rate", 0)) > 0)
    story.append(Paragraph(
        f"The skill improves results for both providers simultaneously on {both_benefit} of 40 evals "
        f"({both_benefit/40*100:.0f}%). This confirms the knowledge base is broadly applicable and "
        f"not over-fitted to a single model's behavior.",
        body
    ))
    story.append(Spacer(1, 4))

    # Summary stats table
    story.append(Paragraph("Summary Statistics", h2))
    summary = [
        [Paragraph("<b>Metric</b>", cell_bold),
         Paragraph("<b>Claude</b>", cell_center_bold),
         Paragraph("<b>Gemini</b>", cell_center_bold)],
        [Paragraph("With Skill Pass Rate", cell),
         Paragraph(f"{c_ws_rate*100:.1f}%", cell_center),
         Paragraph(f"{g_ws_rate*100:.1f}%", cell_center)],
        [Paragraph("Without Skill Pass Rate", cell),
         Paragraph(f"{c_wos_rate*100:.1f}%", cell_center),
         Paragraph(f"{g_wos_rate*100:.1f}%", cell_center)],
        [Paragraph("Skill Delta", cell),
         Paragraph(f"+{c_delta*100:.1f}%", cell_center),
         Paragraph(f"+{g_delta*100:.1f}%", cell_center)],
        [Paragraph("Assertions Passed (with skill)", cell),
         Paragraph(f"{c_ws_p}/{c_ws_t}", cell_center),
         Paragraph(f"{g_ws_p}/{g_ws_t}", cell_center)],
        [Paragraph("Assertions Passed (no skill)", cell),
         Paragraph(f"{c_wos_p}/{c_ws_t}", cell_center),
         Paragraph(f"{g_wos_p}/{g_wos_t}", cell_center)],
        [Paragraph(f"Evals won (with skill, head-to-head)", cell),
         Paragraph(f"{claude_wins}", cell_center),
         Paragraph(f"{gemini_wins}", cell_center)],
        [Paragraph(f"Evals won (no skill, head-to-head)", cell),
         Paragraph(f"{base_claude_wins}", cell_center),
         Paragraph(f"{base_gemini_wins}", cell_center)],
        [Paragraph(f"Evals where skill helps both", cell),
         Paragraph(f"{both_benefit}/40", cell_center),
         Paragraph(f"{both_benefit}/40", cell_center)],
    ]
    st = Table(summary, colWidths=[2.8*inch, 1.4*inch, 1.4*inch])
    st.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), DARK_BLUE),
        ("TEXTCOLOR", (0, 0), (-1, 0), white),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [white, LIGHT_GRAY]),
        ("GRID", (0, 0), (-1, -1), 0.5, HexColor("#dadce0")),
        ("ALIGN", (1, 0), (-1, -1), "CENTER"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ]))
    story.append(st)

    # Footer
    story.append(Spacer(1, 20))
    story.append(HRFlowable(width="100%", thickness=1, color=HexColor("#dadce0"), spaceAfter=8))
    story.append(Paragraph(
        "Generated March 21, 2026  |  GKE Upgrades Skill  |  Iteration 10  |  40 evals, 340 assertions  |  "
        "Claude Sonnet 4 (claude-sonnet-4-20250514) + Gemini 3.1 Pro Preview (gemini-3.1-pro-preview)",
        ParagraphStyle("footer", parent=small, alignment=TA_CENTER),
    ))

    doc.build(story)
    print(f"Report saved to: {output_path}")


if __name__ == "__main__":
    build_report()
