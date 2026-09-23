#!/usr/bin/env python3
"""
Report & Skill Prescription Renderer (`scripts/render_report.py`)

Renders `report.md` with all 11 mandatory review sections and optionally renders
`skill-prescription.md` when `analysis.json["skill_prescription"]` is present.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Dict, List, Optional


def render_report_markdown(evidence: Dict[str, Any], analysis: Dict[str, Any]) -> str:
    case_id = analysis.get("case_id", evidence.get("case_id", "unknown"))
    trial_name = analysis.get("trial_name", evidence.get("trial_name", case_id))
    verdict = analysis.get("verdict", "failed")
    f_stage = analysis.get("failure_stage", "unknown")
    d_stage = analysis.get("detection_stage", "unknown")
    prc = analysis.get("primary_root_cause") or {}
    manifestation = analysis.get("failure_manifestation") or {}
    fud = analysis.get("first_unrecovered_deviation") or {}
    runtime = evidence.get("runtime") or {}

    lines: List[str] = []
    lines.append(f"# Case Failure Analysis Report: `{case_id}` (`{trial_name}`)\n")

    # 1. Executive Summary
    lines.append("## 1. Executive Summary\n")
    lines.append(
        f"- **Verdict**: `{verdict}` (Reward: `{runtime.get('reward')}`)\n"
        f"- **Primary Root Cause**: `{prc.get('category')}` / `{prc.get('subtype')}` (`{prc.get('code')}`, Confidence: **{prc.get('confidence', 0.0):.2f}**)\n"
        f"- **Failure Stage vs Detection Stage**: `{f_stage}` → detected at `{d_stage}`\n"
        f"- **Takeaway**: {prc.get('summary') or manifestation.get('summary') or 'N/A'}\n"
    )

    # 2. Case 状态
    lines.append("## 2. Case 状态\n")
    lines.append("| 属性 | 值 |")
    lines.append("|---|---|")
    lines.append(f"| `case_id` | `{case_id}` |")
    lines.append(f"| `trial_name` | `{trial_name}` |")
    lines.append(f"| `exit_status` | `{runtime.get('exit_status')}` |")
    lines.append(f"| `reward` | `{runtime.get('reward')}` |")
    lines.append(f"| `agent_started` | `{runtime.get('agent_started')}` |")
    lines.append(f"| `verifier_started` | `{runtime.get('verifier_started')}` |")
    lines.append(f"| `started_at` | `{runtime.get('started_at')}` |")
    lines.append(f"| `finished_at` | `{runtime.get('finished_at')}` |\n")

    # 3. 执行时间线
    lines.append("## 3. 执行时间线\n")
    if fud:
        lines.append(
            f"> **首次不可恢复偏离点 (`first_unrecovered_deviation`)**: `{fud.get('event_ref')}` "
            f"({fud.get('timestamp') or 'N/A'}) — {fud.get('summary')}\n"
        )
    timeline = evidence.get("timeline") or []
    if timeline:
        lines.append("| Event ID | Timestamp | Actor | Type | Tool / Summary | Source Pointer |")
        lines.append("|---|---|---|---|---|---|")
        for ev in timeline[:25]:
            cmd_summary = (ev.get("command") or ev.get("observation") or "")[:80].replace("\n", " ").replace("|", "\\|")
            lines.append(
                f"| `{ev.get('event_id')}` | `{ev.get('timestamp') or '-'}` | `{ev.get('actor')}` | "
                f"`{ev.get('event_type')}` | {cmd_summary} | `{ev.get('source_file')}:{ev.get('source_pointer')}` |"
            )
        if len(timeline) > 25:
            lines.append(f"\n*（共 {len(timeline)} 个时间线事件，详见 `evidence.json`）*\n")
    else:
        lines.append("- 无 Agent 轨迹事件（Agent 启动前已终止或 `agent/trajectory.json` 缺失）。\n")

    # 4. 直接失败现象
    lines.append("## 4. 直接失败现象\n")
    lines.append(f"- **表现类型 (`type`)**: `{manifestation.get('type', 'unknown')}`")
    lines.append(f"- **表现摘要 (`summary`)**: {manifestation.get('summary', 'N/A')}\n")
    for vobs in evidence.get("verifier_observations") or []:
        if vobs.get("type") == "verifier_fail_message":
            lines.append("```text")
            lines.append(vobs.get("matched_text", "").strip())
            lines.append("```\n")

    # 5. 主根因
    lines.append("## 5. 主根因\n")
    lines.append(f"- **Category**: `{prc.get('category')}`")
    lines.append(f"- **Subtype**: `{prc.get('subtype')}`")
    lines.append(f"- **Standard Code**: `{prc.get('code')}`")
    lines.append(f"- **Confidence**: `{prc.get('confidence', 0.0):.2f}`")
    lines.append(f"- **因果机制说明**: {prc.get('summary', 'N/A')}\n")

    # 6. 伴随因素
    lines.append("## 6. 伴随因素\n")
    cfs = analysis.get("contributing_factors") or []
    if cfs:
        for cf in cfs:
            lines.append(
                f"- **`{cf.get('category')}` / `{cf.get('code')}`** (Confidence: `{cf.get('confidence', 0.0):.2f}`): "
                f"{cf.get('summary')}"
            )
    else:
        lines.append("- 无次要伴随根因（单一主根因即可完全解释该失败）。")

    sigs = evidence.get("behavioral_signals") or []
    if sigs:
        lines.append("\n**提取到的客观行为信号 (`behavioral_signals`)**:")
        for sig in sigs:
            lines.append(f"- `{sig.get('signal_id')}` (`{sig.get('signal_type')}`): {sig.get('description')} [`{sig.get('event_ref')}`]")
    lines.append("")

    # 7. 证据链
    lines.append("## 7. 证据链\n")
    lines.append("### 7.1 契约审计矩阵 (`Contract Matrix`)\n")
    contracts = evidence.get("contract_observations") or []
    if contracts:
        lines.append("| Contract Item | Prompt 要求 | Verifier 要求 | Agent 输出状态 | 结论 (`alignment`) | 说明 |")
        lines.append("|---|---|---|---|---|---|")
        for c in contracts:
            lines.append(
                f"| `{c.get('item')}` | `{c.get('prompt_requirement')}` | `{c.get('verifier_requirement')}` | "
                f"`{c.get('agent_output_status')}` | **`{c.get('alignment')}`** | {c.get('details', '').replace('|', '\\|')} |"
            )
        lines.append("")
    else:
        lines.append("- 未触发契约检查项（执行在进入契约验证前已中止）。\n")

    lines.append("### 7.2 核心引用证据 (`evidence_refs`)\n")
    for ref in analysis.get("evidence_refs") or []:
        lines.append(f"- `{ref}`")
    lines.append("")

    # 8. 排除的假设
    lines.append("## 8. 排除的假设\n")
    ex_hyps = analysis.get("excluded_hypotheses") or []
    if ex_hyps:
        for eh in ex_hyps:
            lines.append(
                f"- **`{eh.get('hypothesis_id', 'H')}` (`{eh.get('category')}`)**: {eh.get('reason')}"
            )
    else:
        lines.append("- 无其他竞争假设被排除。")
    lines.append("")

    # 9. 建议修复责任方
    lines.append("## 9. 建议修复责任方\n")
    recs = analysis.get("recommended_actions") or []
    if recs:
        for r in recs:
            lines.append(f"- **[{r.get('owner', 'General')}]**: {r.get('action')}")
    else:
        lines.append("- 无需修复。")
    lines.append("")

    # 10. Skill 处方
    lines.append("## 10. Skill 处方\n")
    sp = analysis.get("skill_prescription")
    if sp and isinstance(sp, dict):
        rec_skill = sp.get("recommended_skill") or sp
        lines.append(f"- **生成状态**: 已生成 (`skill-prescription.md`) — 建议新增/更新领域 Skill `{rec_skill.get('name')}`")
        lines.append(f"- **能力缺口 (`capability_gap`)**: {', '.join(rec_skill.get('capability_gap') or [])}")
    else:
        lines.append(
            f"- **生成状态**: **不生成领域 Skill**（主根因属于 `{prc.get('category')}` / `{prc.get('code')}`，"
            "根据 `skill-prescription-policy.md`，非可复用 Agent 能力缺失严禁通过领域 Skill 掩盖 Infra/Verifier/Case 问题）。"
        )
    lines.append("")

    # 11. 缺失证据与分析限制
    lines.append("## 11. 缺失证据与分析限制\n")
    missing = evidence.get("missing_artifacts") or []
    if missing:
        lines.append("- **缺失的 Artifacts**: " + ", ".join(f"`{m}`" for m in missing))
    else:
        lines.append("- 所有标准 Job / Trial / Task 核心文件均完整存在。")
    lines.append("- **分析模式**: 默认静态只读取证分析（未重跑昂贵科学计算）。\n")

    return "\n".join(lines)


def render_skill_prescription_markdown(skill_prescription: Dict[str, Any]) -> str:
    rec = skill_prescription.get("recommended_skill") or skill_prescription
    lines = [
        f"# Skill Prescription: `{rec.get('name', 'domain-skill')}`\n",
        "```yaml",
        "recommended_skill:",
        f"  name: {rec.get('name', 'domain-skill')}",
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
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="Render report.md and optional skill-prescription.md.")
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
    args = parser.parse_args()

    evidence = json.loads(args.evidence.read_text(encoding="utf-8"))
    analysis = json.loads(args.analysis.read_text(encoding="utf-8"))

    report_md = render_report_markdown(evidence, analysis)
    args.output_report.parent.mkdir(parents=True, exist_ok=True)
    args.output_report.write_text(report_md, encoding="utf-8")

    sp = analysis.get("skill_prescription")
    if sp and args.output_prescription:
        args.output_prescription.write_text(render_skill_prescription_markdown(sp), encoding="utf-8")


if __name__ == "__main__":
    main()
