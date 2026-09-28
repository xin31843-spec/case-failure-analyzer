#!/usr/bin/env python3
"""
Report & Skill Prescription Renderer (`scripts/render_report.py`)

Renders:
  - `report.md` (`lang="bilingual"`): Combined Chinese-English bilingual report (4 core sections)
  - `report.zh.md` (`lang="zh"`): Standalone pure Chinese report (4 core sections)
  - `report.en.md` (`lang="en"`): Standalone pure English report (4 core sections)
  - `skill-prescription.md`, `skill-prescription.zh.md`, `skill-prescription.en.md` (when eligible)
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Set


def escape_md_cell(val: Any) -> str:
    if val is None:
        return "-"
    return str(val).replace("\r", " ").replace("\n", " ").replace("|", "\\|").strip()


def select_timeline_events(
    timeline: List[Dict[str, Any]],
    fud_ref: Optional[str],
    limit: int = 25,
) -> List[Dict[str, Any]]:
    """
    Selects up to `limit` timeline events while preserving chronological order:
      - Head events (initial instruction & setup)
      - Context window around `first_unrecovered_deviation` (`fud_ref`) and `shell_error` events
      - Tail events (final steps & verification outcome)
    """
    n = len(timeline)
    if n <= limit:
        return timeline

    keep_indices: Set[int] = set()
    head_count = min(6, max(2, limit // 4))
    tail_count = min(8, max(3, limit // 3))

    for i in range(head_count):
        keep_indices.add(i)
    for i in range(max(0, n - tail_count), n):
        keep_indices.add(i)

    if fud_ref:
        for idx, ev in enumerate(timeline):
            if ev.get("event_id") == fud_ref:
                for w in range(max(0, idx - 2), min(n, idx + 3)):
                    keep_indices.add(w)
                break

    for idx, ev in enumerate(timeline):
        if len(keep_indices) >= limit:
            break
        if ev.get("event_type") == "shell_error" or (ev.get("exit_code") not in (None, 0)):
            keep_indices.add(idx)

    idx_finger = head_count
    while len(keep_indices) < limit and idx_finger < n:
        keep_indices.add(idx_finger)
        idx_finger += 1

    sorted_indices = sorted(keep_indices)[:limit]
    if fud_ref:
        fud_idx = next((i for i, ev in enumerate(timeline) if ev.get("event_id") == fud_ref), None)
        if fud_idx is not None and fud_idx not in sorted_indices:
            sorted_indices[-1] = fud_idx
            sorted_indices.sort()
    return [timeline[i] for i in sorted_indices]


def render_report_markdown(
    evidence: Dict[str, Any],
    analysis: Dict[str, Any],
    lang: str = "bilingual",
) -> str:
    if lang == "en":
        return _render_english_edition(evidence, analysis, standalone=True)
    if lang == "zh":
        return _render_chinese_bilingual_core(evidence, analysis, include_en_labels=False)

    # Default `bilingual`: Part I (Chinese-English side-by-side with canonical 4 section headers)
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
    exec_status = runtime.get("execution_status", runtime.get("exit_status"))

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

    # 1. 诊断结论与运行态概览 (Merges Executive Summary + Case Status + Primary Root Cause without duplication)
    sec1_title = (
        "## 1. 诊断结论与运行态概览 (Verdict & Root Cause Summary)\n"
        if include_en_labels
        else "## 1. 诊断结论与运行态概览\n"
    )
    lines.append(sec1_title)
    if include_en_labels:
        lines.append(
            f"- **Verdict & Gate / 最终裁定与运行门控**: `{verdict}` "
            f"(Execution: `{exec_status}`, Verification: `{runtime.get('verification_status', 'unknown')}`, "
            f"Reward: `{runtime.get('reward')}`, `agent_started={runtime.get('agent_started')}`, "
            f"`verifier_started={runtime.get('verifier_started')}`)\n"
            f"- **Primary Root Cause / 唯一主根因**: `{prc.get('category')}` / `{prc.get('subtype')}` "
            f"(`{prc.get('code')}`, Confidence: **{conf_val:.2f}** [`{conf_kind}`, strength=`{ev_strength}`])\n"
            f"- **Stage Transition / 发生阶段 → 检出阶段**: `{f_stage}` → `{d_stage}` "
            f"(`{runtime.get('started_at') or '-'}` ~ `{runtime.get('finished_at') or '-'}`)\n"
            f"- **Causal Mechanism / 因果传导机制**: {prc.get('summary') or manifestation.get('summary') or 'N/A'}\n"
        )
    else:
        lines.append(
            f"- **最终裁定与运行门控**: `{verdict}` "
            f"（执行状态: `{exec_status}`，验证状态: `{runtime.get('verification_status', 'unknown')}`，"
            f"得分: `{runtime.get('reward')}`，`agent_started={runtime.get('agent_started')}`，"
            f"`verifier_started={runtime.get('verifier_started')}`）\n"
            f"- **唯一主根因**: `{prc.get('category')}` / `{prc.get('subtype')}` "
            f"（`{prc.get('code')}`，证据置信度: **{conf_val:.2f}** [`{conf_kind}`, 强度=`{ev_strength}`]）\n"
            f"- **发生阶段 → 检出阶段**: `{f_stage}` → `{d_stage}` "
            f"（`{runtime.get('started_at') or '-'}` ~ `{runtime.get('finished_at') or '-'}`）\n"
            f"- **因果传导机制**: {prc.get('summary') or manifestation.get('summary') or 'N/A'}\n"
        )

    # 2. 故障现场与因果证据链 (Merges Direct Manifestation + Deviation/Timeline + Contract Matrix/Evidence Refs)
    sec2_title = (
        "## 2. 故障现场与因果证据链 (Failure Manifestation & Evidence Chain)\n"
        if include_en_labels
        else "## 2. 故障现场与因果证据链\n"
    )
    lines.append(sec2_title)
    lines.append(
        f"- **直接失败现象 (`{manifestation.get('type', 'unknown')}`)**: {manifestation.get('summary', 'N/A')}"
    )
    for vobs in evidence.get("verifier_observations") or []:
        if vobs.get("type") == "verifier_fail_message" and (vobs.get("matched_text") or "").strip():
            lines.append("```text")
            lines.append(vobs.get("matched_text", "").strip())
            lines.append("```")

    fud_ref: Optional[str] = None
    if fud:
        fud_status = fud.get("status", "identified" if fud.get("event_ref") else "not_identified")
        fud_ref = fud.get("event_ref")
        lines.append(
            f"- **首次不可恢复偏离点 (`first_unrecovered_deviation`)**: "
            f"status=`{fud_status}`, ref=`{fud_ref or 'N/A'}` "
            f"({fud.get('timestamp') or 'N/A'}) — {fud.get('summary')}"
        )

    ev_refs = analysis.get("evidence_refs") or ["art:trial_result"]
    lines.append("- **核心证据引用 (`evidence_refs`)**: " + ", ".join(f"`{r}`" for r in ev_refs) + "\n")

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
                f"\n*（共 {len(timeline)} 个时间线事件，已保留关键偏离点与首尾上下文，完整事件见 `evidence.json`）*"
            )
        lines.append("")

    contracts = evidence.get("contract_observations") or []
    if contracts:
        lines.append("| 契约项 (Contract Item) | Prompt 要求 | Verifier 要求 | Agent 状态 | 一致性 (`alignment`) | 说明 |")
        lines.append("|---|---|---|---|---|---|")
        for c in contracts:
            lines.append(
                f"| `{escape_md_cell(c.get('item'))}` | `{escape_md_cell(c.get('prompt_requirement'))}` | "
                f"`{escape_md_cell(c.get('verifier_requirement'))}` | `{escape_md_cell(c.get('agent_output_status'))}` | "
                f"**`{escape_md_cell(c.get('alignment'))}`** | {escape_md_cell(c.get('details', ''))} |"
            )
        lines.append("")

    # 3. 竞争假设裁决与伴随信号 (Merges Competing/Excluded Hypotheses + Contributing Factors/Behavioral Signals)
    sec3_title = (
        "## 3. 竞争假设裁决与伴随信号 (Hypothesis Audit & Signals)\n"
        if include_en_labels
        else "## 3. 竞争假设裁决与伴随信号\n"
    )
    lines.append(sec3_title)
    comp_hyps = analysis.get("competing_hypotheses") or []
    for ch in comp_hyps:
        lines.append(
            f"- **候选假设 `{ch.get('hypothesis_id', 'H')}` (`{ch.get('category')}` / `{ch.get('subtype')}`, "
            f"Score: `{float(ch.get('confidence', 0.0)):.2f}`)**: {ch.get('claim')} "
            f"(支持: `{ch.get('evidence_for')}`, 反驳: `{ch.get('evidence_against')}`)"
        )
    ex_hyps = analysis.get("excluded_hypotheses") or []
    for eh in ex_hyps:
        lines.append(
            f"- **排除假设 `{eh.get('hypothesis_id', 'H')}` (`{eh.get('category')}`)**: {eh.get('reason')}"
        )
    if not comp_hyps and not ex_hyps:
        lines.append("- 用例已通过验证，无竞争性失败假设。")

    cfs = analysis.get("contributing_factors") or []
    for cf in cfs:
        lines.append(
            f"- **伴随因素 (`{cf.get('category')}` / `{cf.get('code')}`, "
            f"Confidence: `{float(cf.get('confidence', 0.0)):.2f}`)**: {cf.get('summary')}"
        )

    sigs = evidence.get("behavioral_signals") or []
    for sig in sigs:
        lines.append(
            f"- **行为信号 `{sig.get('signal_id')}` (`{sig.get('signal_type')}`)**: "
            f"{sig.get('description')} [`{sig.get('event_ref')}`]"
        )
    lines.append("")

    # 4. 修复行动与处方建议 (Merges Recommended Actions + Optional Skill Prescription + Optional Missing Artifacts)
    sec4_title = (
        "## 4. 修复行动与处方建议 (Recommended Actions & Notes)\n"
        if include_en_labels
        else "## 4. 修复行动与处方建议\n"
    )
    lines.append(sec4_title)
    recs = analysis.get("recommended_actions") or []
    if recs:
        for r in recs:
            lines.append(f"- **[{r.get('owner', 'General')}]**: {r.get('action')}")
    else:
        lines.append("- 无需修复（用例已通过验证）。")

    sp = analysis.get("skill_prescription")
    if sp and isinstance(sp, dict):
        rec_skill = sp.get("recommended_skill") or sp
        lines.append(
            f"- **领域 Skill 处方 (`skill-prescription.md`)**: 建议新增/更新可复用技能 `{rec_skill.get('name')}` "
            f"（能力缺口: {', '.join(rec_skill.get('capability_gap') or [])}）"
        )

    missing = evidence.get("missing_artifacts") or []
    if missing:
        lines.append("- **缺失产物 (`missing_artifacts`)**: " + ", ".join(f"`{m}`" for m in missing))
    lines.append("")

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
    exec_status = runtime.get("execution_status", runtime.get("exit_status"))

    def _sec_header(num: int, title: str) -> str:
        if standalone:
            return f"## {num}. {title}\n"
        return f"### E{num}. {title}\n"

    lines: List[str] = []
    if standalone:
        lines.append(f"# Case Failure Analysis Report: `{case_id}` (`{trial_name}`)\n")
    else:
        lines.append("# Part II: English Edition\n")

    # 1. Verdict & Root Cause Summary
    lines.append(_sec_header(1, "Verdict & Root Cause Summary"))
    lines.append(
        f"- **Verdict & Gate**: `{verdict}` (Execution: `{exec_status}`, "
        f"Verification: `{runtime.get('verification_status', 'unknown')}`, Reward: `{runtime.get('reward')}`, "
        f"`agent_started={runtime.get('agent_started')}`, `verifier_started={runtime.get('verifier_started')}`)\n"
        f"- **Primary Root Cause**: `{prc.get('category')}` / `{prc.get('subtype')}` "
        f"(`{prc.get('code')}`, Confidence: **{conf_val:.2f}** [`{conf_kind}`, strength=`{ev_strength}`])\n"
        f"- **Stage Transition**: `{f_stage}` → detected at `{d_stage}` "
        f"(`{runtime.get('started_at') or '-'}` ~ `{runtime.get('finished_at') or '-'}`)\n"
        f"- **Causal Mechanism**: {prc.get('summary') or manifestation.get('summary') or 'N/A'}\n"
    )

    # 2. Failure Manifestation & Evidence Chain
    lines.append(_sec_header(2, "Failure Manifestation & Evidence Chain"))
    lines.append(
        f"- **Direct Failure Manifestation (`{manifestation.get('type', 'unknown')}`)**: {manifestation.get('summary', 'N/A')}"
    )
    for vobs in evidence.get("verifier_observations") or []:
        if vobs.get("type") == "verifier_fail_message" and (vobs.get("matched_text") or "").strip():
            lines.append("```text")
            lines.append(vobs.get("matched_text", "").strip())
            lines.append("```")

    fud_ref: Optional[str] = None
    if fud:
        fud_status = fud.get("status", "identified" if fud.get("event_ref") else "not_identified")
        fud_ref = fud.get("event_ref")
        lines.append(
            f"- **First Unrecovered Deviation (`first_unrecovered_deviation`)**: "
            f"status=`{fud_status}`, ref=`{fud_ref or 'N/A'}` "
            f"({fud.get('timestamp') or 'N/A'}) — {fud.get('summary')}"
        )

    ev_refs = analysis.get("evidence_refs") or ["art:trial_result"]
    lines.append("- **Evidence References (`evidence_refs`)**: " + ", ".join(f"`{r}`" for r in ev_refs) + "\n")

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
                f"\n*(Total {len(timeline)} timeline events; key deviation and boundary events retained, see `evidence.json` for full list)*"
            )
        lines.append("")

    contracts = evidence.get("contract_observations") or []
    if contracts:
        lines.append("| Contract Item | Prompt Req | Verifier Req | Agent Output Status | Alignment | Details |")
        lines.append("|---|---|---|---|---|---|")
        for c in contracts:
            lines.append(
                f"| `{escape_md_cell(c.get('item'))}` | `{escape_md_cell(c.get('prompt_requirement'))}` | "
                f"`{escape_md_cell(c.get('verifier_requirement'))}` | `{escape_md_cell(c.get('agent_output_status'))}` | "
                f"**`{escape_md_cell(c.get('alignment'))}`** | {escape_md_cell(c.get('details', ''))} |"
            )
        lines.append("")

    # 3. Hypothesis Audit & Signals
    lines.append(_sec_header(3, "Hypothesis Audit & Signals"))
    comp_hyps = analysis.get("competing_hypotheses") or []
    for ch in comp_hyps:
        lines.append(
            f"- **Candidate `{ch.get('hypothesis_id')}` (`{ch.get('category')}` / `{ch.get('subtype')}`, "
            f"Score: `{float(ch.get('confidence', 0.0)):.2f}`)**: {ch.get('claim')} "
            f"[for=`{ch.get('evidence_for')}`, against=`{ch.get('evidence_against')}`]"
        )
    ex_hyps = analysis.get("excluded_hypotheses") or []
    for eh in ex_hyps:
        lines.append(f"- **Excluded `{eh.get('hypothesis_id')}` (`{eh.get('category')}`)**: {eh.get('reason')}")
    if not comp_hyps and not ex_hyps:
        lines.append("- Case passed; no competing failure hypotheses.")

    for cf in analysis.get("contributing_factors") or []:
        lines.append(
            f"- **Contributing Factor (`{cf.get('category')}` / `{cf.get('code')}`, "
            f"Confidence: `{float(cf.get('confidence', 0.0)):.2f}`)**: {cf.get('summary')}"
        )
    for sig in evidence.get("behavioral_signals") or []:
        lines.append(
            f"- **Behavioral Signal `{sig.get('signal_id')}` (`{sig.get('signal_type')}`)**: "
            f"{sig.get('description')} [`{sig.get('event_ref')}`]"
        )
    lines.append("")

    # 4. Recommended Actions & Notes
    lines.append(_sec_header(4, "Recommended Actions & Notes"))
    recs = analysis.get("recommended_actions") or []
    if recs:
        for r in recs:
            lines.append(f"- **[{r.get('owner', 'General')}]**: {r.get('action')}")
    else:
        lines.append("- No remediation required (case passed).")

    sp = analysis.get("skill_prescription")
    if sp and isinstance(sp, dict):
        rec_skill = sp.get("recommended_skill") or sp
        lines.append(
            f"- **Domain Skill Prescription (`skill-prescription.md`)**: Recommended skill `{rec_skill.get('name')}` "
            f"(Capability Gap: {', '.join(rec_skill.get('capability_gap') or [])})"
        )

    missing = evidence.get("missing_artifacts") or []
    if missing:
        lines.append("- **Missing Artifacts (`missing_artifacts`)**: " + ", ".join(f"`{m}`" for m in missing))
    lines.append("")
    return "\n".join(lines)


def render_skill_prescription_markdown(
    skill_prescription: Dict[str, Any],
    lang: str = "bilingual",
) -> str:
    rec = skill_prescription.get("recommended_skill") or skill_prescription
    name = rec.get("name", "domain-skill")

    yaml_lines = [
        "```yaml",
        "recommended_skill:",
        f"  name: {name}",
        "  trigger:",
    ]
    for t in rec.get("trigger") or []:
        yaml_lines.append(f'    - "{t}"')
    yaml_lines.append("  capability_gap:")
    for g in rec.get("capability_gap") or []:
        yaml_lines.append(f'    - "{g}"')
    yaml_lines.append("  required_guidance:")
    for rg in rec.get("required_guidance") or []:
        yaml_lines.append(f'    - "{rg}"')
    yaml_lines.append("  anti_patterns:")
    for ap in rec.get("anti_patterns") or []:
        yaml_lines.append(f'    - "{ap}"')
    yaml_lines.append("  evidence_cases:")
    for ec in rec.get("evidence_cases") or []:
        yaml_lines.append(f'    - "{ec}"')
    yaml_lines.append("```\n")
    yaml_block = "\n".join(yaml_lines)

    zh_section = "\n".join(
        [
            f"- **建议技能名称**: `{name}`",
            "- **触发条件 (`trigger`)**: " + "；".join(rec.get("trigger") or []),
            "- **能力缺口 (`capability_gap`)**: " + "；".join(rec.get("capability_gap") or []),
            "- **核心执行指引 (`required_guidance`)**: " + "；".join(rec.get("required_guidance") or []),
            "- **禁止的反模式 (`anti_patterns`)**: " + "；".join(rec.get("anti_patterns") or []),
            "",
        ]
    )

    en_section = "\n".join(
        [
            f"- **Recommended Skill Name**: `{name}`",
            "- **Trigger Conditions (`trigger`)**: " + "; ".join(rec.get("trigger") or []),
            "- **Capability Gap (`capability_gap`)**: " + "; ".join(rec.get("capability_gap") or []),
            "- **Required Guidance (`required_guidance`)**: " + "; ".join(rec.get("required_guidance") or []),
            "- **Anti-Patterns to Avoid (`anti_patterns`)**: " + "; ".join(rec.get("anti_patterns") or []),
            "",
        ]
    )

    if lang == "zh":
        return f"# 领域技能处方 (`Skill Prescription`): `{name}`\n\n## 1. 结构化定义 (YAML)\n\n{yaml_block}\n## 2. 中文执行指引\n\n{zh_section}"
    if lang == "en":
        return f"# Domain Skill Prescription: `{name}`\n\n## 1. Structured Specification (YAML)\n\n{yaml_block}\n## 2. Execution Guidance\n\n{en_section}"

    return (
        f"# Skill Prescription / 领域技能处方 (中英双版): `{name}`\n\n"
        f"## 1. Structured Specification (YAML)\n\n{yaml_block}\n"
        f"## 2. 中文说明 (Chinese Guidance)\n\n{zh_section}\n"
        f"## 3. English Guidance\n\n{en_section}"
    )


def main() -> None:
    import sys
    from validate_analysis import validate_all

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

    if not args.evidence.is_file():
        print(f"ERROR: --evidence file does not exist: {args.evidence}", file=sys.stderr)
        sys.exit(2)
    if not args.analysis.is_file():
        print(f"ERROR: --analysis file does not exist: {args.analysis}", file=sys.stderr)
        sys.exit(2)

    evidence = json.loads(args.evidence.read_text(encoding="utf-8"))
    analysis = json.loads(args.analysis.read_text(encoding="utf-8"))

    report_md = render_report_markdown(evidence, analysis, lang=args.lang)
    ok, val_errors = validate_all(evidence, analysis, report_md)
    if not ok:
        for err in val_errors:
            print(f"VALIDATION ERROR: {err}", file=sys.stderr)
        sys.exit(1)

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
        args.output_prescription.write_text(
            render_skill_prescription_markdown(sp, lang="bilingual"), encoding="utf-8"
        )
        if args.output_prescription.name == "skill-prescription.md":
            (args.output_prescription.parent / "skill-prescription.zh.md").write_text(
                render_skill_prescription_markdown(sp, lang="zh"), encoding="utf-8"
            )
            (args.output_prescription.parent / "skill-prescription.en.md").write_text(
                render_skill_prescription_markdown(sp, lang="en"), encoding="utf-8"
            )


if __name__ == "__main__":
    main()
