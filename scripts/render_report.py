#!/usr/bin/env python3
"""
Report & Skill Prescription Renderer (`scripts/render_report.py`)

Renders Chinese-English bilingual `report.md` (along with standalone `report.zh.md`
and `report.en.md` editions) containing all 11 mandatory review sections, and
optionally renders bilingual `skill-prescription.md` when `analysis.json["skill_prescription"]`
is present.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Dict, List, Optional


def escape_md_cell(val: Any) -> str:
    if val is None:
        return "-"
    return str(val).replace("\r", " ").replace("\n", " ").replace("|", "\\|").strip()


def select_timeline_events(
    timeline: List[Dict[str, Any]],
    fud_ref: Optional[str],
    limit: int = 25,
) -> List[Dict[str, Any]]:
    if len(timeline) <= limit:
        return timeline
    selected = list(timeline[:limit])
    if fud_ref and not any(ev.get("event_id") == fud_ref for ev in selected):
        fud_ev = next((ev for ev in timeline if ev.get("event_id") == fud_ref), None)
        if fud_ev is not None:
            selected = selected[: limit - 1] + [fud_ev]
    return selected


def render_report_markdown(
    evidence: Dict[str, Any],
    analysis: Dict[str, Any],
    lang: str = "bilingual",
) -> str:
    if lang == "en":
        return _render_english_edition(evidence, analysis, standalone=True)
    if lang == "zh":
        return _render_chinese_bilingual_core(evidence, analysis, include_en_labels=False)

    # Default `bilingual`: Part I (Chinese-English side-by-side with canonical 11 section headers)
    # followed by Part II (Complete English Edition)
    part_zh_bi = _render_chinese_bilingual_core(evidence, analysis, include_en_labels=True)
    part_en = _render_english_edition(evidence, analysis, standalone=False)
    return f"{part_zh_bi}\n---\n\n{part_en}"


def _render_chinese_bilingual_core(
    evidence: Dict[str, Any],
    analysis: Dict[str, Any],
    include_en_labels: bool = True,
) -> str:
    case_id = analysis.get("case_id", evidence.get("case_id", "unknown"))
    trial_name = analysis.get("trial_name", evidence.get("trial_name", case_id))
    verdict = analysis.get("verdict", "failed")
    f_stage = analysis.get("failure_stage", "unknown")
    d_stage = analysis.get("detection_stage", "unknown")
    prc = analysis.get("primary_root_cause") or {}
    manifestation = analysis.get("failure_manifestation") or {}
    fud = analysis.get("first_unrecovered_deviation") or {}
    runtime = evidence.get("runtime") or {}
    conf_val = float(prc.get("confidence", 0.0))
    conf_kind = prc.get("confidence_kind", "heuristic_evidence_score")
    ev_strength = prc.get("evidence_strength", "medium")

    lines: List[str] = []
    if include_en_labels:
        lines.append(
            f"# Case Failure Analysis Report / 案例失败因果审计报告: `{case_id}` (`{trial_name}`)\n"
        )
        lines.append(
            "> **Language / 语言版本**: 中英双语对照版 (Chinese-English Bilingual Edition) — "
            "[Jump to Part II: Complete English Edition](#part-ii-english-edition)\n"
        )
    else:
        lines.append(f"# 案例失败因果审计报告: `{case_id}` (`{trial_name}`)\n")

    # 1. Executive Summary
    lines.append("## 1. Executive Summary\n")
    lines.append(
        f"- **Verdict / 最终裁定**: `{verdict}` "
        f"(Execution: `{runtime.get('execution_status', runtime.get('exit_status'))}`, "
        f"Verification: `{runtime.get('verification_status', 'unknown')}`, "
        f"Reward: `{runtime.get('reward')}`)\n"
        f"- **Primary Root Cause / 主根因**: `{prc.get('category')}` / `{prc.get('subtype')}` "
        f"(`{prc.get('code')}`, Confidence: **{conf_val:.2f}** [{conf_kind}, strength=`{ev_strength}`])\n"
        f"- **Failure Stage vs Detection Stage / 发生阶段与暴露阶段**: `{f_stage}` → detected at `{d_stage}`\n"
        f"- **Takeaway (EN/ZH)**: {prc.get('summary') or manifestation.get('summary') or 'N/A'}\n"
    )

    # 2. Case 状态
    sec2_title = "## 2. Case 状态 (Case & Trial Runtime Status)\n" if include_en_labels else "## 2. Case 状态\n"
    lines.append(sec2_title)
    lines.append("| 属性 (Property) | 值 (Value) |")
    lines.append("|---|---|")
    lines.append(f"| `case_id` | `{escape_md_cell(case_id)}` |")
    lines.append(f"| `trial_name` | `{escape_md_cell(trial_name)}` |")
    lines.append(f"| `execution_status` | `{escape_md_cell(runtime.get('execution_status', runtime.get('exit_status')))}` |")
    lines.append(f"| `verification_status` | `{escape_md_cell(runtime.get('verification_status'))}` |")
    lines.append(f"| `exit_status` | `{escape_md_cell(runtime.get('exit_status'))}` |")
    lines.append(f"| `reward` | `{escape_md_cell(runtime.get('reward'))}` |")
    lines.append(f"| `agent_started` | `{escape_md_cell(runtime.get('agent_started'))}` |")
    lines.append(f"| `verifier_started` | `{escape_md_cell(runtime.get('verifier_started'))}` |")
    lines.append(f"| `started_at` | `{escape_md_cell(runtime.get('started_at'))}` |")
    lines.append(f"| `finished_at` | `{escape_md_cell(runtime.get('finished_at'))}` |\n")

    # 3. 执行时间线
    sec3_title = "## 3. 执行时间线 (Execution Timeline)\n" if include_en_labels else "## 3. 执行时间线\n"
    lines.append(sec3_title)
    if fud:
        fud_status = fud.get("status", "identified" if fud.get("event_ref") else "not_identified")
        fud_ref = fud.get("event_ref")
        lines.append(
            f"> **首次不可恢复偏离点 / First Unrecovered Deviation (`first_unrecovered_deviation`)**: "
            f"status=`{fud_status}`, ref=`{fud_ref or 'N/A'}` "
            f"({fud.get('timestamp') or 'N/A'}) — {fud.get('summary')}\n"
        )
    else:
        fud_ref = None

    timeline = evidence.get("timeline") or []
    if timeline:
        displayed_events = select_timeline_events(timeline, fud_ref, limit=25)
        lines.append("| Event ID | Timestamp | Actor | Type | Tool / Summary | Source Pointer |")
        lines.append("|---|---|---|---|---|---|")
        for ev in displayed_events:
            cmd_summary = escape_md_cell((ev.get("command") or ev.get("observation") or "")[:80])
            lines.append(
                f"| `{escape_md_cell(ev.get('event_id'))}` | `{escape_md_cell(ev.get('timestamp') or '-')}` | "
                f"`{escape_md_cell(ev.get('actor'))}` | `{escape_md_cell(ev.get('event_type'))}` | "
                f"{cmd_summary} | `{escape_md_cell(ev.get('source_file'))}:{escape_md_cell(ev.get('source_pointer'))}` |"
            )
        if len(timeline) > len(displayed_events):
            lines.append(
                f"\n*（共 {len(timeline)} 个时间线事件，已保留关键偏离点，完整事件见 `evidence.json` / "
                f"Total {len(timeline)} timeline events; key deviation retained, see `evidence.json` for full list）*\n"
            )
    else:
        if runtime.get("agent_started"):
            lines.append(
                "- Agent 已启动（存在 `claude-code.txt` 或执行阶段记录），但 `agent/trajectory.json` 无结构化步骤事件 / "
                "Agent started (`agent_started=True`), but `agent/trajectory.json` contains no structured step events.\n"
            )
        else:
            lines.append(
                "- 无 Agent 轨迹事件（Agent 启动前已终止且 `agent/trajectory.json` 未生成） / "
                "No Agent trajectory events (`agent_started=False`; terminated prior to agent startup).\n"
            )

    # 4. 直接失败现象
    sec4_title = "## 4. 直接失败现象 (Direct Failure Manifestation)\n" if include_en_labels else "## 4. 直接失败现象\n"
    lines.append(sec4_title)
    lines.append(f"- **表现类型 (`type`)**: `{manifestation.get('type', 'unknown')}`")
    lines.append(f"- **表现摘要 (`summary`)**: {manifestation.get('summary', 'N/A')}\n")
    for vobs in evidence.get("verifier_observations") or []:
        if vobs.get("type") == "verifier_fail_message":
            lines.append("```text")
            lines.append(vobs.get("matched_text", "").strip())
            lines.append("```\n")

    # 5. 主根因
    sec5_title = "## 5. 主根因 (Primary Root Cause)\n" if include_en_labels else "## 5. 主根因\n"
    lines.append(sec5_title)
    lines.append(f"- **Category / 类别**: `{prc.get('category')}`")
    lines.append(f"- **Subtype / 子类**: `{prc.get('subtype')}`")
    lines.append(f"- **Standard Code / 标准编码**: `{prc.get('code')}`")
    lines.append(
        f"- **Confidence / 证据评分**: `{conf_val:.2f}` (`{conf_kind}`, Evidence Strength: `{ev_strength}`)"
    )
    lines.append(f"- **因果机制说明 / Causal Mechanism**: {prc.get('summary', 'N/A')}\n")

    # 6. 伴随因素
    sec6_title = "## 6. 伴随因素 (Contributing Factors & Behavioral Signals)\n" if include_en_labels else "## 6. 伴随因素\n"
    lines.append(sec6_title)
    cfs = analysis.get("contributing_factors") or []
    if cfs:
        for cf in cfs:
            lines.append(
                f"- **`{cf.get('category')}` / `{cf.get('code')}`** "
                f"(Confidence: `{float(cf.get('confidence', 0.0)):.2f}`): {cf.get('summary')}"
            )
    else:
        lines.append(
            "- 无次要伴随根因（单一主根因即可解释该状态） / "
            "No secondary contributing root causes identified."
        )

    sigs = evidence.get("behavioral_signals") or []
    if sigs:
        lines.append("\n**提取到的客观行为信号 (`behavioral_signals`)**:")
        for sig in sigs:
            lines.append(
                f"- `{sig.get('signal_id')}` (`{sig.get('signal_type')}`): "
                f"{sig.get('description')} [`{sig.get('event_ref')}`]"
            )
    lines.append("")

    # 7. 证据链
    sec7_title = "## 7. 证据链 (Evidence Chain & Contract Matrix)\n" if include_en_labels else "## 7. 证据链\n"
    lines.append(sec7_title)
    lines.append("### 7.1 契约审计矩阵 (`Contract Matrix`)\n")
    contracts = evidence.get("contract_observations") or []
    if contracts:
        lines.append(
            "| Contract Item | Prompt 要求 (Prompt Req) | Verifier 要求 (Verifier Req) | "
            "Agent 输出状态 (Agent Status) | 结论 (`alignment`) | 说明 (Details) |"
        )
        lines.append("|---|---|---|---|---|---|")
        for c in contracts:
            lines.append(
                f"| `{escape_md_cell(c.get('item'))}` | `{escape_md_cell(c.get('prompt_requirement'))}` | "
                f"`{escape_md_cell(c.get('verifier_requirement'))}` | `{escape_md_cell(c.get('agent_output_status'))}` | "
                f"**`{escape_md_cell(c.get('alignment'))}`** | {escape_md_cell(c.get('details', ''))} |"
            )
        lines.append("")
    else:
        lines.append(
            "- 未触发契约检查项（执行在进入契约验证前已中止或无额外契约项） / "
            "No contract matrix observations triggered.\n"
        )

    lines.append("### 7.2 核心引用证据 (`evidence_refs`)\n")
    ev_refs = analysis.get("evidence_refs") or []
    if ev_refs:
        for ref in ev_refs:
            lines.append(f"- `{ref}`")
    else:
        lines.append("- `art:trial_result`")
    lines.append("")

    # 8. 排除的假设
    sec8_title = "## 8. 排除的假设 (Competing & Excluded Hypotheses)\n" if include_en_labels else "## 8. 排除的假设\n"
    lines.append(sec8_title)
    comp_hyps = analysis.get("competing_hypotheses") or []
    if comp_hyps:
        lines.append("### 8.1 竞争假设评估 (`competing_hypotheses`)\n")
        for ch in comp_hyps:
            lines.append(
                f"- **`{ch.get('hypothesis_id', 'H')}` (`{ch.get('category')}` / `{ch.get('subtype')}`, "
                f"Score: `{float(ch.get('confidence', 0.0)):.2f}`)**: {ch.get('claim')} "
                f"(For: `{ch.get('evidence_for')}`, Against: `{ch.get('evidence_against')}`)"
            )
        lines.append("")

    ex_hyps = analysis.get("excluded_hypotheses") or []
    if ex_hyps:
        lines.append("### 8.2 已排除假设 (`excluded_hypotheses`)\n")
        for eh in ex_hyps:
            lines.append(
                f"- **`{eh.get('hypothesis_id', 'H')}` (`{eh.get('category')}`)**: {eh.get('reason')}"
            )
    elif not comp_hyps:
        lines.append("- 无其他竞争假设被排除 / No competing hypotheses excluded.")
    lines.append("")

    # 9. 建议修复责任方
    sec9_title = "## 9. 建议修复责任方 (Recommended Actions by Owner)\n" if include_en_labels else "## 9. 建议修复责任方\n"
    lines.append(sec9_title)
    recs = analysis.get("recommended_actions") or []
    if recs:
        for r in recs:
            lines.append(f"- **[{r.get('owner', 'General')}]**: {r.get('action')}")
    else:
        lines.append("- 无需修复（用例已通过） / No remediation required (case passed).")
    lines.append("")

    # 10. Skill 处方
    sec10_title = "## 10. Skill 处方 (Domain Skill Prescription)\n" if include_en_labels else "## 10. Skill 处方\n"
    lines.append(sec10_title)
    sp = analysis.get("skill_prescription")
    if sp and isinstance(sp, dict):
        rec_skill = sp.get("recommended_skill") or sp
        lines.append(
            f"- **生成状态 / Status**: 已生成 (`skill-prescription.md`) — "
            f"建议新增/更新领域 Skill `{rec_skill.get('name')}` / "
            f"Generated (`skill-prescription.md`) for reusable domain skill `{rec_skill.get('name')}`"
        )
        lines.append(
            f"- **能力缺口 (`capability_gap`)**: {', '.join(rec_skill.get('capability_gap') or [])}"
        )
    else:
        lines.append(
            f"- **生成状态 / Status**: **不生成领域 Skill / Not Generated**（主根因属于 `{prc.get('category')}` / `{prc.get('code')}`；"
            "根据 `skill-prescription-policy.md`，非可复用 Agent 能力缺失严禁通过领域 Skill 掩盖 Infra/Verifier/Case 问题 / "
            "Per `skill-prescription-policy.md`, domain skills are strictly restricted to reusable Agent capability gaps）。"
        )
    lines.append("")

    # 11. 缺失证据与分析限制
    sec11_title = "## 11. 缺失证据与分析限制 (Missing Evidence & Analysis Limitations)\n" if include_en_labels else "## 11. 缺失证据与分析限制\n"
    lines.append(sec11_title)
    missing = evidence.get("missing_artifacts") or []
    if missing:
        lines.append("- **缺失的 Artifacts (`missing_artifacts`)**: " + ", ".join(f"`{m}`" for m in missing))
    else:
        lines.append(
            "- 所有标准 Job / Trial / Task 核心文件均完整存在 / "
            "All standard Job, Trial, and Task artifacts are present."
        )
    lines.append(
        "- **分析模式 / Analysis Mode**: 默认静态只读取证与竞争假设裁决（未重跑昂贵科学计算） / "
        "Static read-only forensic extraction and competing hypothesis evaluation.\n"
    )

    return "\n".join(lines)


def _render_english_edition(
    evidence: Dict[str, Any],
    analysis: Dict[str, Any],
    standalone: bool = False,
) -> str:
    case_id = analysis.get("case_id", evidence.get("case_id", "unknown"))
    trial_name = analysis.get("trial_name", evidence.get("trial_name", case_id))
    verdict = analysis.get("verdict", "failed")
    f_stage = analysis.get("failure_stage", "unknown")
    d_stage = analysis.get("detection_stage", "unknown")
    prc = analysis.get("primary_root_cause") or {}
    manifestation = analysis.get("failure_manifestation") or {}
    fud = analysis.get("first_unrecovered_deviation") or {}
    runtime = evidence.get("runtime") or {}
    conf_val = float(prc.get("confidence", 0.0))
    conf_kind = prc.get("confidence_kind", "heuristic_evidence_score")
    ev_strength = prc.get("evidence_strength", "medium")

    lines: List[str] = []
    if standalone:
        lines.append(f"# Case Failure Analysis Report (English Edition): `{case_id}` (`{trial_name}`)\n")
    else:
        lines.append("# Part II: English Edition\n")

    lines.append("### E1. Executive Summary\n")
    lines.append(
        f"- **Verdict**: `{verdict}` (Execution: `{runtime.get('execution_status', runtime.get('exit_status'))}`, "
        f"Verification: `{runtime.get('verification_status', 'unknown')}`, Reward: `{runtime.get('reward')}`)\n"
        f"- **Primary Root Cause**: `{prc.get('category')}` / `{prc.get('subtype')}` "
        f"(`{prc.get('code')}`, Confidence: **{conf_val:.2f}** [{conf_kind}, strength=`{ev_strength}`])\n"
        f"- **Failure Stage vs Detection Stage**: `{f_stage}` → detected at `{d_stage}`\n"
        f"- **Takeaway**: {prc.get('summary') or manifestation.get('summary') or 'N/A'}\n"
    )

    lines.append("### E2. Case & Runtime Status\n")
    lines.append(
        f"- **Agent Started**: `{runtime.get('agent_started')}` | **Verifier Started**: `{runtime.get('verifier_started')}`\n"
        f"- **Started At**: `{runtime.get('started_at')}` | **Finished At**: `{runtime.get('finished_at')}`\n"
    )

    lines.append("### E3. Execution Timeline & First Unrecovered Deviation\n")
    if fud:
        lines.append(
            f"- **First Unrecovered Deviation**: status=`{fud.get('status', 'identified')}`, "
            f"ref=`{fud.get('event_ref') or 'N/A'}` — {fud.get('summary')}\n"
        )
    else:
        lines.append("- **First Unrecovered Deviation**: None (case passed).\n")

    lines.append("### E4. Direct Failure Manifestation\n")
    lines.append(f"- **Manifestation Type**: `{manifestation.get('type', 'unknown')}`")
    lines.append(f"- **Summary**: {manifestation.get('summary', 'N/A')}\n")

    lines.append("### E5. Primary Root Cause & Causal Mechanism\n")
    lines.append(
        f"- **Classification**: `{prc.get('category')}` → `{prc.get('subtype')}` (`{prc.get('code')}`)\n"
        f"- **Causal Explanation**: {prc.get('summary', 'N/A')}\n"
    )

    lines.append("### E6. Contributing Factors & Behavioral Signals\n")
    cfs = analysis.get("contributing_factors") or []
    if cfs:
        for cf in cfs:
            lines.append(f"- **`{cf.get('category')}` / `{cf.get('code')}`**: {cf.get('summary')}")
    else:
        lines.append("- No secondary contributing root causes.")
    lines.append("")

    lines.append("### E7. Evidence Chain\n")
    for ref in analysis.get("evidence_refs") or ["art:trial_result"]:
        lines.append(f"- `{ref}`")
    lines.append("")

    lines.append("### E8. Competing & Excluded Hypotheses\n")
    for ch in analysis.get("competing_hypotheses") or []:
        lines.append(
            f"- **`{ch.get('hypothesis_id')}` (`{ch.get('category')}`)**: {ch.get('claim')} "
            f"[score={float(ch.get('confidence', 0.0)):.2f}]"
        )
    for eh in analysis.get("excluded_hypotheses") or []:
        lines.append(f"- **Excluded `{eh.get('hypothesis_id')}` (`{eh.get('category')}`)**: {eh.get('reason')}")
    if not (analysis.get("competing_hypotheses") or analysis.get("excluded_hypotheses")):
        lines.append("- None.")
    lines.append("")

    lines.append("### E9. Recommended Remediation Actions\n")
    for r in analysis.get("recommended_actions") or []:
        lines.append(f"- **[{r.get('owner', 'General')}]**: {r.get('action')}")
    if not (analysis.get("recommended_actions") or []):
        lines.append("- None required.")
    lines.append("")

    lines.append("### E10. Domain Skill Prescription\n")
    sp = analysis.get("skill_prescription")
    if sp and isinstance(sp, dict):
        rec_skill = sp.get("recommended_skill") or sp
        lines.append(f"- **Recommended Skill**: `{rec_skill.get('name')}` (see `skill-prescription.md`)")
    else:
        lines.append(f"- **Status**: Not generated (root cause category is `{prc.get('category')}`).")
    lines.append("")

    lines.append("### E11. Missing Evidence & Limitations\n")
    missing = evidence.get("missing_artifacts") or []
    lines.append(
        "- **Missing Artifacts**: " + (", ".join(f"`{m}`" for m in missing) if missing else "None") + "\n"
    )
    return "\n".join(lines)


def render_skill_prescription_markdown(skill_prescription: Dict[str, Any]) -> str:
    rec = skill_prescription.get("recommended_skill") or skill_prescription
    name = rec.get("name", "domain-skill")
    lines = [
        f"# Skill Prescription / 领域技能处方 (中英双版): `{name}`\n",
        "## 1. Structured Specification (YAML)\n",
        "```yaml",
        "recommended_skill:",
        f"  name: {name}",
        "  trigger:",
    ]
    for t in rec.get("trigger") or []:
        lines.append(f'    - "{t}"')
    lines.append("  capability_gap:")
    for g in rec.get("capability_gap") or []:
        lines.append(f'    - "{g}"')
    lines.append("  required_guidance:")
    for rg in rec.get("required_guidance") or []:
        lines.append(f'    - "{rg}"')
    lines.append("  anti_patterns:")
    for ap in rec.get("anti_patterns") or []:
        lines.append(f'    - "{ap}"')
    lines.append("  evidence_cases:")
    for ec in rec.get("evidence_cases") or []:
        lines.append(f'    - "{ec}"')
    lines.append("```\n")

    lines.append("## 2. 中文说明 (Chinese Guidance)\n")
    lines.append(f"- **建议技能名称**: `{name}`")
    lines.append("- **触发条件 (Triggers)**: " + "；".join(rec.get("trigger") or []))
    lines.append("- **能力缺口 (Capability Gap)**: " + "；".join(rec.get("capability_gap") or []))
    lines.append("- **核心执行指引 (Required Guidance)**: " + "；".join(rec.get("required_guidance") or []))
    lines.append("- **禁止的反模式 (Anti-Patterns)**: " + "；".join(rec.get("anti_patterns") or []))
    lines.append("")

    lines.append("## 3. English Guidance\n")
    lines.append(f"- **Recommended Skill Name**: `{name}`")
    lines.append("- **Trigger Conditions**: " + "; ".join(rec.get("trigger") or []))
    lines.append("- **Capability Gap**: " + "; ".join(rec.get("capability_gap") or []))
    lines.append("- **Required Guidance**: " + "; ".join(rec.get("required_guidance") or []))
    lines.append("- **Anti-Patterns to Avoid**: " + "; ".join(rec.get("anti_patterns") or []))
    lines.append("")

    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="Render bilingual report.md and optional skill-prescription.md.")
    parser.add_argument("--evidence", required=True, type=Path, help="Path to evidence.json")
    parser.add_argument("--analysis", required=True, type=Path, help="Path to analysis.json")
    parser.add_argument("--output-report", required=True, type=Path, help="Path to write report.md")
    parser.add_argument(
        "--output-prescription",
        required=False,
        type=Path,
        default=None,
        help="Optional path to write skill-prescription.md",
    )
    parser.add_argument(
        "--lang",
        choices=["bilingual", "zh", "en"],
        default="bilingual",
        help="Report language edition (default: bilingual)",
    )
    args = parser.parse_args()

    evidence = json.loads(args.evidence.read_text(encoding="utf-8"))
    analysis = json.loads(args.analysis.read_text(encoding="utf-8"))

    report_md = render_report_markdown(evidence, analysis, lang=args.lang)
    args.output_report.parent.mkdir(parents=True, exist_ok=True)
    args.output_report.write_text(report_md, encoding="utf-8")

    # Also emit companion report.zh.md and report.en.md when rendering standard report.md
    if args.output_report.name == "report.md":
        (args.output_report.parent / "report.zh.md").write_text(
            render_report_markdown(evidence, analysis, lang="zh"), encoding="utf-8"
        )
        (args.output_report.parent / "report.en.md").write_text(
            render_report_markdown(evidence, analysis, lang="en"), encoding="utf-8"
        )

    sp = analysis.get("skill_prescription")
    if sp and args.output_prescription:
        args.output_prescription.write_text(render_skill_prescription_markdown(sp), encoding="utf-8")


if __name__ == "__main__":
    main()
