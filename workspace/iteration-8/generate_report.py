#!/usr/bin/env python3
"""Generate iteration-8 PDF report for GKE Upgrades Skill."""

from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.lib.colors import HexColor, white, black
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
    PageBreak, HRFlowable
)
import json


# Colors
BLUE = HexColor("#1a73e8")
DARK_BLUE = HexColor("#174ea6")
LIGHT_BLUE = HexColor("#e8f0fe")
GREEN = HexColor("#1e8e3e")
LIGHT_GREEN = HexColor("#e6f4ea")
RED = HexColor("#d93025")
LIGHT_RED = HexColor("#fce8e6")
GRAY = HexColor("#5f6368")
LIGHT_GRAY = HexColor("#f1f3f4")
DARK = HexColor("#202124")


def build_report():
    output_path = "/sessions/hopeful-optimistic-galileo/mnt/code/gke-upgrades-skill/workspace/iteration-8/iteration-8-report.pdf"
    doc = SimpleDocTemplate(
        output_path,
        pagesize=letter,
        topMargin=0.75*inch,
        bottomMargin=0.75*inch,
        leftMargin=0.75*inch,
        rightMargin=0.75*inch,
    )

    styles = getSampleStyleSheet()

    # Custom styles
    title_style = ParagraphStyle(
        "CustomTitle", parent=styles["Title"],
        fontSize=24, textColor=DARK_BLUE, spaceAfter=6,
        fontName="Helvetica-Bold",
    )
    subtitle_style = ParagraphStyle(
        "Subtitle", parent=styles["Normal"],
        fontSize=12, textColor=GRAY, spaceAfter=20,
        fontName="Helvetica",
    )
    h1 = ParagraphStyle(
        "H1", parent=styles["Heading1"],
        fontSize=16, textColor=DARK_BLUE, spaceBefore=20, spaceAfter=10,
        fontName="Helvetica-Bold",
    )
    h2 = ParagraphStyle(
        "H2", parent=styles["Heading2"],
        fontSize=13, textColor=BLUE, spaceBefore=14, spaceAfter=8,
        fontName="Helvetica-Bold",
    )
    body = ParagraphStyle(
        "Body", parent=styles["Normal"],
        fontSize=10, textColor=DARK, spaceAfter=8,
        fontName="Helvetica", leading=14,
    )
    body_bold = ParagraphStyle(
        "BodyBold", parent=body,
        fontName="Helvetica-Bold",
    )
    small = ParagraphStyle(
        "Small", parent=body,
        fontSize=8.5, textColor=GRAY, leading=11,
    )
    cell_style = ParagraphStyle(
        "Cell", parent=body,
        fontSize=9, leading=11, spaceAfter=0,
    )
    cell_bold = ParagraphStyle(
        "CellBold", parent=cell_style,
        fontName="Helvetica-Bold",
    )
    cell_center = ParagraphStyle(
        "CellCenter", parent=cell_style,
        alignment=TA_CENTER,
    )
    cell_center_bold = ParagraphStyle(
        "CellCenterBold", parent=cell_center,
        fontName="Helvetica-Bold",
    )

    story = []

    # ── Title ──
    story.append(Paragraph("GKE Upgrades Skill", title_style))
    story.append(Paragraph("Iteration 8 Benchmark Report  |  March 21, 2026", subtitle_style))
    story.append(HRFlowable(width="100%", thickness=2, color=BLUE, spaceAfter=16))

    # ── Executive Summary ──
    story.append(Paragraph("Executive Summary", h1))
    story.append(Paragraph(
        "Iteration 8 incorporates authoritative knowledge base content from the GKE PM group and "
        "engineering team inside Google. Seven source documents (PDFs, CSV, JSON, TXT) were consumed "
        "and synthesized into SKILL.md and GEMINI.md, with eval assertions refined to reflect the "
        "deeper, more nuanced PM-validated content. The result is a skill grounded in internal Google "
        "source material covering new features shipping in March-April 2026, detailed node pool "
        "upgrade strategy descriptions, persistent maintenance exclusions, cluster disruption budgets, "
        "accelerated patching, the upgrade info API, and AI/ML host maintenance handler mechanisms.",
        body
    ))
    story.append(Spacer(1, 6))

    # ── Headline metrics box ──
    headline_data = [
        [
            Paragraph("<b>With Skill</b>", cell_center_bold),
            Paragraph("<b>Without Skill</b>", cell_center_bold),
            Paragraph("<b>Delta</b>", cell_center_bold),
            Paragraph("<b>Evals</b>", cell_center_bold),
            Paragraph("<b>Assertions</b>", cell_center_bold),
        ],
        [
            Paragraph("75.0%", ParagraphStyle("big", parent=cell_center, fontSize=18, fontName="Helvetica-Bold", textColor=GREEN)),
            Paragraph("49.7%", ParagraphStyle("big2", parent=cell_center, fontSize=18, fontName="Helvetica-Bold", textColor=GRAY)),
            Paragraph("+25.3%", ParagraphStyle("big3", parent=cell_center, fontSize=18, fontName="Helvetica-Bold", textColor=BLUE)),
            Paragraph("40", ParagraphStyle("big4", parent=cell_center, fontSize=18, fontName="Helvetica-Bold")),
            Paragraph("340", ParagraphStyle("big5", parent=cell_center, fontSize=18, fontName="Helvetica-Bold")),
        ],
    ]
    ht = Table(headline_data, colWidths=[1.4*inch]*5)
    ht.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), DARK_BLUE),
        ("TEXTCOLOR", (0, 0), (-1, 0), white),
        ("BACKGROUND", (0, 1), (-1, 1), LIGHT_BLUE),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("GRID", (0, 0), (-1, -1), 0.5, BLUE),
        ("TOPPADDING", (0, 1), (-1, 1), 10),
        ("BOTTOMPADDING", (0, 1), (-1, 1), 10),
    ]))
    story.append(ht)
    story.append(Spacer(1, 16))

    # ── Iteration History ──
    story.append(Paragraph("Iteration History", h1))
    iter_data = [
        [Paragraph("<b>Iteration</b>", cell_center_bold),
         Paragraph("<b>With Skill</b>", cell_center_bold),
         Paragraph("<b>Without Skill</b>", cell_center_bold),
         Paragraph("<b>Delta</b>", cell_center_bold),
         Paragraph("<b>Evals</b>", cell_center_bold),
         Paragraph("<b>Assertions</b>", cell_center_bold)],
        [Paragraph("4", cell_center), Paragraph("80.4%", cell_center), Paragraph("71.1%", cell_center),
         Paragraph("+9.3%", cell_center), Paragraph("23", cell_center), Paragraph("194", cell_center)],
        [Paragraph("5", cell_center), Paragraph("83.5%", cell_center), Paragraph("55.8%", cell_center),
         Paragraph("+27.7%", cell_center), Paragraph("37", cell_center), Paragraph("310", cell_center)],
        [Paragraph("6", cell_center), Paragraph("82.6%", cell_center), Paragraph("56.8%", cell_center),
         Paragraph("+25.8%", cell_center), Paragraph("37", cell_center), Paragraph("310", cell_center)],
        [Paragraph("7", cell_center), Paragraph("77.8%", cell_center), Paragraph("50.9%", cell_center),
         Paragraph("+26.9%", cell_center), Paragraph("40", cell_center), Paragraph("338", cell_center)],
        [Paragraph("<b>8</b>", cell_center_bold), Paragraph("<b>75.0%</b>", cell_center_bold),
         Paragraph("<b>49.7%</b>", cell_center_bold), Paragraph("<b>+25.3%</b>", cell_center_bold),
         Paragraph("<b>40</b>", cell_center_bold), Paragraph("<b>340</b>", cell_center_bold)],
    ]
    it = Table(iter_data, colWidths=[1.0*inch, 1.2*inch, 1.2*inch, 1.0*inch, 0.8*inch, 1.0*inch])
    it.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), DARK_BLUE),
        ("TEXTCOLOR", (0, 0), (-1, 0), white),
        ("BACKGROUND", (0, -1), (-1, -1), LIGHT_GREEN),
        ("ROWBACKGROUNDS", (0, 1), (-1, -2), [white, LIGHT_GRAY]),
        ("GRID", (0, 0), (-1, -1), 0.5, HexColor("#dadce0")),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
    ]))
    story.append(it)
    story.append(Spacer(1, 6))
    story.append(Paragraph(
        "Note: The with-skill absolute score has decreased from iteration 5 (83.5%) because assertions "
        "have become progressively harder as PM-specific nuances were added. The delta remains strong at "
        "+25.3%, confirming the skill provides substantial value. The without-skill baseline also dropped "
        "(49.7% vs 55.8% in iter-5), confirming the assertions are genuinely harder.",
        small
    ))

    # ── Per-Eval Breakdown ──
    story.append(PageBreak())
    story.append(Paragraph("Per-Eval Results (Iteration 8)", h1))
    story.append(Paragraph(
        "Each eval tests a distinct GKE upgrade scenario. Scores show assertions passed out of total. "
        "The delta column shows the skill's impact on that specific eval.",
        body
    ))
    story.append(Spacer(1, 6))

    # Load benchmark
    with open("/sessions/hopeful-optimistic-galileo/mnt/code/gke-upgrades-skill/workspace/iteration-8/benchmark.json") as f:
        bm = json.load(f)

    ws_map = {e["eval_id"]: e for e in bm["with_skill"]["evals"]}
    wos_map = {e["eval_id"]: e for e in bm["without_skill"]["evals"]}

    eval_ids = sorted(ws_map.keys())

    per_eval_header = [
        Paragraph("<b>Eval</b>", cell_center_bold),
        Paragraph("<b>With Skill</b>", cell_center_bold),
        Paragraph("<b>Without Skill</b>", cell_center_bold),
        Paragraph("<b>Delta</b>", cell_center_bold),
    ]

    # Split into two halves for two-column display
    half = 20
    left_ids = eval_ids[:half]
    right_ids = eval_ids[half:]

    def make_eval_table(ids):
        rows = [per_eval_header]
        for eid in ids:
            ws = ws_map[eid]
            wos = wos_map[eid]
            delta = ws["pass_rate"] - wos["pass_rate"]
            delta_str = f"+{delta*100:.0f}%" if delta >= 0 else f"{delta*100:.0f}%"
            delta_color = GREEN if delta > 0 else (RED if delta < 0 else GRAY)
            rows.append([
                Paragraph(f"{eid}", cell_center),
                Paragraph(f"{ws['pass_count']}/{ws['total']} ({ws['pass_rate']*100:.0f}%)", cell_center),
                Paragraph(f"{wos['pass_count']}/{wos['total']} ({wos['pass_rate']*100:.0f}%)", cell_center),
                Paragraph(f"<font color='{delta_color}'>{delta_str}</font>", cell_center),
            ])
        t = Table(rows, colWidths=[0.6*inch, 1.2*inch, 1.2*inch, 0.7*inch])
        t.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), DARK_BLUE),
            ("TEXTCOLOR", (0, 0), (-1, 0), white),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [white, LIGHT_GRAY]),
            ("GRID", (0, 0), (-1, -1), 0.5, HexColor("#dadce0")),
            ("ALIGN", (0, 0), (-1, -1), "CENTER"),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("TOPPADDING", (0, 0), (-1, -1), 4),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ]))
        return t

    # Place two tables side by side
    left_table = make_eval_table(left_ids)
    right_table = make_eval_table(right_ids)

    combined = Table([[left_table, right_table]], colWidths=[3.7*inch, 3.7*inch])
    combined.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
    ]))
    story.append(combined)

    # Top / bottom performers
    story.append(Spacer(1, 14))
    story.append(Paragraph("Performance Highlights", h2))

    perfect = [eid for eid in eval_ids if ws_map[eid]["pass_rate"] == 1.0]
    low = sorted(eval_ids, key=lambda x: ws_map[x]["pass_rate"])[:5]
    biggest_delta = sorted(eval_ids, key=lambda x: ws_map[x]["pass_rate"] - wos_map[x]["pass_rate"], reverse=True)[:5]

    story.append(Paragraph(
        f"<b>Perfect scores (100%):</b> Evals {', '.join(str(e) for e in perfect)}",
        body
    ))
    story.append(Paragraph(
        f"<b>Lowest with-skill scores:</b> Eval {low[0]} ({ws_map[low[0]]['pass_rate']*100:.0f}%), "
        f"Eval {low[1]} ({ws_map[low[1]]['pass_rate']*100:.0f}%), "
        f"Eval {low[2]} ({ws_map[low[2]]['pass_rate']*100:.0f}%)",
        body
    ))
    story.append(Paragraph(
        f"<b>Biggest skill impact:</b> Eval {biggest_delta[0]} "
        f"(+{(ws_map[biggest_delta[0]]['pass_rate'] - wos_map[biggest_delta[0]]['pass_rate'])*100:.0f}%), "
        f"Eval {biggest_delta[1]} "
        f"(+{(ws_map[biggest_delta[1]]['pass_rate'] - wos_map[biggest_delta[1]]['pass_rate'])*100:.0f}%), "
        f"Eval {biggest_delta[2]} "
        f"(+{(ws_map[biggest_delta[2]]['pass_rate'] - wos_map[biggest_delta[2]]['pass_rate'])*100:.0f}%)",
        body
    ))

    # ── Knowledge Base Sources ──
    story.append(PageBreak())
    story.append(Paragraph("Knowledge Base Sources", h1))
    story.append(Paragraph(
        "All content in the kb/ directory was consumed as authoritative input from the GKE PM group "
        "and engineering team inside Google. Each source was read, synthesized, and incorporated into "
        "SKILL.md and GEMINI.md. Below is a description of each source and what knowledge it contributed.",
        body
    ))
    story.append(Spacer(1, 8))

    sources = [
        {
            "name": "pm_feedback.txt",
            "type": "Text file",
            "author": "GKE PM Group",
            "desc": (
                "Detailed FAQ-style PM feedback covering the full GKE upgrade lifecycle. This was the "
                "richest single source, providing authoritative answers on control plane patch controls "
                "(90-day retention after patch removal, recurrence interval), the new maintenance window "
                "duration gcloud syntax (effective April 2026), nodepool upgrade concurrency (preview end "
                "of March 2026), scheduled upgrade notifications (preview March 24), Extended channel cost "
                "model (extra cost only during extended period), detailed descriptions of all three node pool "
                "upgrade strategies (surge, blue-green, autoscaled blue-green with wait-for-drain), persistent "
                "exclusion flag, per-cluster vs per-nodepool exclusion guidance, exclusion translation warnings "
                "between no-channel and release channels, accelerated patch auto-upgrades, and version "
                "terminology clarifications."
            ),
            "contributed": [
                "CP patch controls (90-day retention, recurrence interval)",
                "Maintenance window duration gcloud syntax",
                "Nodepool upgrade concurrency (preview)",
                "Scheduled upgrade notifications (preview)",
                "Blue-green and autoscaled blue-green strategy details",
                "Persistent exclusions (--add-maintenance-exclusion-until-end-of-support)",
                "Cluster disruption budget (patch 7d/90d, minor 30d/90d)",
                "Accelerated patch auto-upgrades (--patch-update=accelerated)",
                "Per-cluster vs per-nodepool exclusion guidance",
                "Exclusion translation warnings (no-channel to release channels)",
            ],
        },
        {
            "name": "feedback-iteration6.json",
            "type": "JSON file",
            "author": "GKE PM Group",
            "desc": (
                "Per-eval PM feedback from iteration 6 covering 14 evals (23-30, 36). Provided specific "
                "corrections and additions: PDB timeout behavior and eviction blocked notifications, "
                "exclusion translation warnings during no-channel migration, the distinction between default "
                "version and auto-upgrade target, legacy channel EoS enforcement behavior, persistent "
                "exclusions with no 6-month maximum, channel promotion cadence details, scope distinctions "
                "between no_minor and no_minor_or_nodes, the get-upgrade-info API, and the guidance that "
                "limited GPU capacity means no blue-green (requires 2x resources)."
            ),
            "contributed": [
                "PDB timeout + eviction blocked notifications",
                "Legacy channel EoS enforcement specifics",
                "get-upgrade-info API details",
                "Limited capacity = no blue-green guidance for GPU pools",
                "Refined eval assertions for evals 23-30, 36",
            ],
        },
        {
            "name": "GKE Upgrades (go_gke-safe-upgrades).pdf",
            "type": "PDF (internal presentation)",
            "author": "Aurelie Fonteny, GKE PM",
            "desc": (
                "Internal 'GKE Upgrades as Non-Events' presentation. Comprehensive best practices framework "
                "covering the four pillars: choose your pace, control timing, continuous rollouts, reduce "
                "disruption. Includes the safe-upgrade cheat sheet, release channel comparison tables, "
                "version promotion path (Rapid to Regular to Stable to Extended), No channel vs Release "
                "channel feature comparison, maintenance windows and exclusions, persistent exclusions, "
                "cluster disruption budget, rollout sequencing evolution (5 stages), two-step CP upgrade "
                "with rollback, and upgrade visibility tools (GUI portal, upgrade info API, notifications, "
                "recommendations, Cloud Hub maintenance portal)."
            ),
            "contributed": [
                "Version promotion path (Rapid -> Regular -> Stable -> Extended)",
                "Two-step CP minor upgrade details",
                "Rollout sequencing evolution (5 stages)",
                "Upgrade visibility tools and notifications",
                "Safe-upgrade best practices framework",
            ],
        },
        {
            "name": "GKE Upgrades - customers.pdf",
            "type": "PDF (customer-facing presentation)",
            "author": "GKE PM Group",
            "desc": (
                "Customer-facing version of the GKE Upgrades presentation. Similar content to the internal "
                "version but sanitized for external audiences. Includes accelerated patch auto-upgrades, "
                "extended support timeline table, scheduled upgrade notifications, and the reliable rollout "
                "and backport policy. Validated that all internal content is consistent with what Google "
                "communicates externally."
            ),
            "contributed": [
                "Extended support timeline table",
                "Accelerated patch auto-upgrade customer guidance",
                "Reliable rollout and backport policy validation",
            ],
        },
        {
            "name": "GKE upgrade roadmap (go_gke-upgrade-roadmap).pdf",
            "type": "PDF (internal roadmap)",
            "author": "GKE Engineering",
            "desc": (
                "GKE Upgrade Directional Roadmap showing H2 2025 (launched) and H1 2026 features. Key "
                "roadmap items: scheduled upgrade notification, CP patch delta transparency, rollout "
                "sequencing with custom stages GA, rollout controls (start/pause/resume), eviction controls "
                "GA, declarative node version, CP maintenance recurrence and version retention, 100-node "
                "100-nodepool parallelism upgrade, 2-step CP GA. Future (2026+): higher scale rollout "
                "sequencing, in-place upgrade with local NVM SSD, CCC declarative nodepool version."
            ),
            "contributed": [
                "100-node 100-nodepool parallelism (roadmap)",
                "CP maintenance recurrence and version retention details",
                "Declarative node version (roadmap)",
                "In-place upgrade with local NVM SSD (roadmap)",
                "Earliest known auto-upgrade date (~2 weeks prior)",
            ],
        },
        {
            "name": "Copy of GKE AI Maintenance and Upgrade User Guide.pdf",
            "type": "PDF (technical guide)",
            "author": "GKE AI/ML Engineering",
            "desc": (
                "Manual GKE accelerator maintenance guide covering the host maintenance mechanism. Details "
                "the cloud.google.com/perform-maintenance=true node label, parallel strategy for training "
                "workloads (~4h per update, all-at-once with scale-to-zero), rolling strategy for inference "
                "workloads (batched by failure domain), scale-to-zero method, host maintenance visibility "
                "via node labels, troubleshooting stuck upgrades, and the gke_updater.sh automation script."
            ),
            "contributed": [
                "GKE AI Host Maintenance handler mechanism",
                "Parallel strategy (training) and rolling strategy (inference)",
                "cloud.google.com/perform-maintenance=true label",
                "Scale-to-zero method for accelerator maintenance",
                "~4h per host maintenance update timing",
            ],
        },
        {
            "name": "Comments at 2026-03-21 14_04 UTC...csv",
            "type": "CSV (Google Doc comments)",
            "author": "GKE Engineering Team",
            "desc": (
                "Exported Google Doc comments from the GKE engineering team reviewing the AI Maintenance "
                "guide. Key discussion threads: autoscaled blue-green for host maintenance, the 20-node "
                "concurrency limit and plans to increase to 100 nodes and 100 nodepools, scale-to-zero as "
                "a method, compact placement concerns during upgrades, controller-based solutions vs scripts "
                "for maintenance automation, and mixed workload cluster considerations for inference and "
                "training on the same cluster."
            ),
            "contributed": [
                "20-node concurrency limit (confirmed, with 100-node roadmap)",
                "Compact placement verification during upgrades",
                "Mixed workload cluster guidance (inference + training)",
                "Controller-based vs script-based maintenance approaches",
            ],
        },
    ]

    for i, src in enumerate(sources):
        # Source header
        story.append(Paragraph(f"{i+1}. {src['name']}", h2))

        meta_data = [[
            Paragraph(f"<b>Type:</b> {src['type']}", cell_style),
            Paragraph(f"<b>Author:</b> {src['author']}", cell_style),
        ]]
        mt = Table(meta_data, colWidths=[3.5*inch, 3.5*inch])
        mt.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), LIGHT_GRAY),
            ("TOPPADDING", (0, 0), (-1, -1), 4),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ("LEFTPADDING", (0, 0), (-1, -1), 8),
        ]))
        story.append(mt)
        story.append(Spacer(1, 4))

        story.append(Paragraph(src["desc"], body))

        # Contributed knowledge
        story.append(Paragraph("<b>Key knowledge contributed:</b>", body_bold))
        for item in src["contributed"]:
            story.append(Paragraph(f"  \u2022  {item}", ParagraphStyle(
                "bullet", parent=body, leftIndent=20, fontSize=9.5,
            )))
        story.append(Spacer(1, 6))

    # ── Changes Made ──
    story.append(PageBreak())
    story.append(Paragraph("Changes Made in Iteration 8", h1))

    changes = [
        ("SKILL.md Updates", [
            "Added version promotion path (Rapid -> Regular -> Stable -> Extended) with release cadence (~1/week)",
            "Added Extended channel cost clarification (extra cost only during extended period)",
            "Added legacy channel EoS behavior details (force-upgrade even with no auto-upgrade)",
            "Added migration warning for exclusion translation between no-channel and release channels",
            "Added per-cluster vs per-nodepool exclusion guidance",
            "Added persistent maintenance exclusions (--add-maintenance-exclusion-until-end-of-support)",
            "Added cluster disruption budget details (patch 7d default/90d max, minor 30d default/90d max)",
            "Added control plane patch controls (90-day retention, recurrence interval)",
            "Added accelerated patch auto-upgrades (--patch-update=accelerated)",
            "Added maintenance window duration gcloud syntax (effective April 2026)",
            "Added upgrade info API (gcloud container clusters get-upgrade-info)",
            "Added blue-green upgrade strategy (separate from autoscaled blue-green)",
            "Enhanced autoscaled blue-green with wait-for-drain, PDB upgrade timeout details",
            "Added GKE AI Host Maintenance handler mechanism (parallel/rolling strategies)",
            "Added nodepool upgrade concurrency (preview, April 2026)",
            "Added scheduled upgrade notifications (preview, March 2026)",
            "Added PDB timeout and eviction blocked notifications",
            "Added limited capacity = no blue-green guidance for GPU pools",
        ]),
        ("GEMINI.md Updates", [
            "Full rewrite incorporating all SKILL.md changes for Gemini CLI parity",
            "Added release channels table with version promotion path",
            "Added maintenance windows and exclusions section with all new features",
            "Added version terminology section with get-upgrade-info API",
            "Added four node pool strategies (surge, blue-green, autoscaled blue-green, manual)",
            "Added GKE AI Host Maintenance section",
            "Added nodepool upgrade concurrency and scheduled notifications",
        ]),
        ("Eval Assertion Updates", [
            "Eval 3: Added PDB timeout and eviction blocked notification assertion",
            "Eval 13: Refined autoscaled blue-green to include wait-for-drain and PDB timeout",
            "Eval 22: Renamed to autoscaled blue-green for consistency",
            "Eval 24: Added exclusion translation warning and Extended as migration path",
            "Eval 25: Refined default vs auto-upgrade target distinction (cluster-specific)",
            "Eval 26: Added legacy channel EoS behavior (force-upgrade even with no auto-upgrade)",
            "Eval 27: Added persistent exclusions and disruption budget details",
            "Eval 28: Added channel promotion cadence and get-upgrade-info API",
            "Eval 29: Refined exclusion scope guidance (no_minor vs no_minor_or_nodes)",
            "Eval 30: Added get-upgrade-info API assertion",
            "Eval 36: Replaced blue-green suggestion with limited capacity guidance",
            "Total assertions increased from 338 to 340",
        ]),
    ]

    for section_title, items in changes:
        story.append(Paragraph(section_title, h2))
        for item in items:
            story.append(Paragraph(f"  \u2022  {item}", ParagraphStyle(
                "changeBullet", parent=body, leftIndent=20, fontSize=9.5, spaceAfter=3,
            )))
        story.append(Spacer(1, 6))

    # ── Footer ──
    story.append(Spacer(1, 20))
    story.append(HRFlowable(width="100%", thickness=1, color=HexColor("#dadce0"), spaceAfter=8))
    story.append(Paragraph(
        "Generated March 21, 2026  |  GKE Upgrades Skill v8  |  40 evals, 340 assertions  |  "
        "Model: claude-sonnet-4-20250514",
        ParagraphStyle("footer", parent=small, alignment=TA_CENTER),
    ))

    doc.build(story)
    print(f"Report saved to: {output_path}")


if __name__ == "__main__":
    build_report()
