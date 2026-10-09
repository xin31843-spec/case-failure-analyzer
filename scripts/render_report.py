#!/usr/bin/env python3
"""
Report, Job Summary & Skill Prescription Renderer (`scripts/render_report.py`)

Renders:
  - `report.md` (`lang="bilingual"`): Compact Chinese-English bilingual report (4 core sections)
  - `report.zh.md` (`lang="zh"`): Standalone pure Chinese report (4 core sections)
  - `report.en.md` (`lang="en"`): Standalone pure English report (4 core sections)
  - `job_summary.md`, `job_summary.zh.md`, `job_summary.en.md` (multi-trial batch dashboard)
  - `skill-prescription.md`, `skill-prescription.zh.md`, `skill-prescription.en.md` (when eligible)
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

_SCRIPT_DIR = Path(__file__).resolve().parent
if str(_SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPT_DIR))

from render_batch import render_job_summary_markdown

__all__ = [
    "CORE_ARTIFACT_BASENAMES",
    "SECONDARY_ARTIFACT_BASENAMES",
    "filter_core_missing_artifacts",
    "format_evidence_list_text",
    "render_job_summary_markdown",
    "render_report_markdown",
    "render_skill_prescription_markdown",
]


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


CATEGORY_LABELS_ZH: Dict[str, str] = {
    "agent": "智能体决策与执行失误 (Agent Decisions & Execution)",
    "case": "基准题目与规格设计缺陷 (Case Specification & Design)",
    "infra": "运行环境与系统设施缺陷 (Environment & Infrastructure)",
    "verifier": "评测验证与规则判定缺陷 (Evaluation & Verifier Logic)",
    "unknown": "未分类或信息缺失 (Unknown/Unclassified)",
    "none": "无 (用例测试通过) (None - Passed)",
}

CATEGORY_LABELS_EN: Dict[str, str] = {
    "agent": "Agent Decisions & Execution",
    "case": "Case Specification & Design",
    "infra": "Environment & Infrastructure",
    "verifier": "Evaluation & Verifier Logic",
    "unknown": "Unknown/Unclassified",
    "none": "None (Passed)",
}

CORE_ARTIFACT_BASENAMES = {
    "trajectory.json",
    "claude-code.txt",
    "verify.log",
    "test-stdout.txt",
    "results.json",
    "result.json",
    "instruction.md",
    "solve.sh",
    "verify.py",
    "refs.json",
}

SECONDARY_ARTIFACT_BASENAMES = {
    "config.json",
    "lock.json",
    "trial.log",
    "job.log",
    "manifest.json",
    ".cfa_manifest.json",
    "exception.txt",
    "runner.log",
    "setup.log",
    "docker.log",
}


def filter_core_missing_artifacts(missing: List[str]) -> Tuple[List[str], int]:
    """
    Filters missing_artifacts to core inputs and calculation outputs only,
    converging internal runtime and temporary files into a summary count.
    Matches against explicit filename basenames, preventing broad substring mismatch.
    """
    core: List[str] = []
    secondary_count = 0
    for item in missing:
        raw = item.split(":", 1)[1] if ":" in item else item
        bname = Path(raw.strip()).name.lower()
        if bname in CORE_ARTIFACT_BASENAMES:
            core.append(item)
        else:
            secondary_count += 1
    return core, secondary_count


def _prune_hypotheses_for_report(
    comp_hyps: List[Dict[str, Any]],
    ex_hyps: List[Dict[str, Any]],
    runtime: Dict[str, Any],
    primary_category: str,
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """
    Prunes low-value or contradictory hypotheses for report display:
      1. If agent never started (runtime.agent_started is False), prunes candidate
         hypotheses claiming 'agent'.
      2. If candidates with positive confidence or non-empty evidence exist,
         filters out 0.0-confidence candidates that have zero evidence.
      3. If all candidates have 0.0 confidence and empty evidence, keeps only the
         top candidate aligned with primary_category (or top 1), pruning irrelevant ones.
    """
    agent_started = bool(runtime.get("agent_started", False))
    pruned_comp: List[Dict[str, Any]] = []

    for ch in comp_hyps:
        cat = ch.get("category", "")
        # Rule 1: Agent never started -> cannot blame agent as candidate hypothesis
        if not agent_started and cat == "agent":
            continue
        pruned_comp.append(ch)

    # Rule 2: If meaningful candidates exist, prune zero-evidence zero-confidence speculative ones
    meaningful = [
        ch
        for ch in pruned_comp
        if float(ch.get("confidence", 0.0)) > 0.0 or bool(ch.get("evidence_for"))
    ]
    if meaningful:
        pruned_comp = meaningful
    elif len(pruned_comp) > 1:
        # All have 0 score and empty evidence: keep only the top matching primary category
        matching = [ch for ch in pruned_comp if ch.get("category") == primary_category]
        if matching:
            pruned_comp = matching[:1]
        else:
            pruned_comp = pruned_comp[:1]

    # Excluded hypotheses
    pruned_ex = list(ex_hyps)

    return pruned_comp, pruned_ex


def format_evidence_list_text(
    ev_for: Optional[List[Any]],
    ev_against: Optional[List[Any]],
    lang: str = "bilingual",
) -> str:
    """
    Formats hypothesis evidence_for and evidence_against into natural human-readable text,
    eliminating Python list repr syntax leaks (e.g. ['art:job_result']).
    """
    ev_for = ev_for or []
    ev_against = ev_against or []
    parts: List[str] = []

    if lang == "zh":
        if ev_for:
            parts.append("支持: " + ", ".join(f"`{x}`" for x in ev_for))
        else:
            parts.append("支持: 无")
        if ev_against:
            parts.append("反驳: " + ", ".join(f"`{x}`" for x in ev_against))
        return f" ({', '.join(parts)})" if parts else ""
    elif lang == "en":
        if ev_for:
            parts.append("for: " + ", ".join(f"`{x}`" for x in ev_for))
        else:
            parts.append("for: none")
        if ev_against:
            parts.append("against: " + ", ".join(f"`{x}`" for x in ev_against))
        return f" [{', '.join(parts)}]" if parts else ""
    else:  # bilingual
        if ev_for:
            parts.append("支持 / For: " + ", ".join(f"`{x}`" for x in ev_for))
        else:
            parts.append("支持 / For: 无")
        if ev_against:
            parts.append("反驳 / Against: " + ", ".join(f"`{x}`" for x in ev_against))
        return f" ({', '.join(parts)})" if parts else ""


def _render_gate_warning(
    runtime: Dict[str, Any],
    verdict: str = "failed",
    lang: str = "bilingual",
) -> Optional[str]:
    """
    Hides normal gate status (agent_started=True, verifier_started=True),
    only emitting a prominent blockquote Warning when pre-startup failed or container aborted.
    """
    if verdict == "passed":
        return None

    agent_started = bool(runtime.get("agent_started", False))
    verifier_started = bool(runtime.get("verifier_started", False))
    exec_status = str(runtime.get("execution_status", runtime.get("exit_status", ""))).lower()

    is_abnormal_container = exec_status in ("container_oom", "container_crash", "setup_failed")
    if agent_started and verifier_started and not is_abnormal_container:
        return None

    if not agent_started:
        if lang == "zh":
            return (
                f"> ⚠️ **运行门控警示**: 智能体未启动 (`agent_started=False`, `verifier_started={verifier_started}`)"
                f"，触发启动前环境或系统设施异常拦截。\n"
            )
        elif lang == "en":
            return (
                f"> ⚠️ **Runtime Gate Warning**: Agent did not start (`agent_started=False`, `verifier_started={verifier_started}`)"
                f"; pre-startup infrastructure or setup exception triggered.\n"
            )
        else:
            return (
                f"> ⚠️ **运行门控警示 (Runtime Gate Warning)**: 智能体未启动 (`agent_started=False`, `verifier_started={verifier_started}`)"
                f"，触发启动前环境/基础设施异常拦截 (Pre-startup interception).\n"
            )
    elif not verifier_started:
        if lang == "zh":
            return (
                "> ⚠️ **运行门控警示**: 评测验证器未启动 (`agent_started=True`, `verifier_started=False`)"
                "，执行在进入评测验证前中断。\n"
            )
        elif lang == "en":
            return (
                "> ⚠️ **Runtime Gate Warning**: Verifier did not start (`agent_started=True`, `verifier_started=False`)"
                "; execution aborted prior to evaluation phase.\n"
            )
        else:
            return (
                "> ⚠️ **运行门控警示 (Runtime Gate Warning)**: 评测验证器未启动 (`agent_started=True`, `verifier_started=False`)"
                "，执行在进入评测验证前中断 (Aborted before verifier execution).\n"
            )
    elif is_abnormal_container:
        if lang == "zh":
            return f"> ⚠️ **运行门控警示**: 容器运行时发生异常中断 (`execution_status={exec_status}`)。\n"
        elif lang == "en":
            return f"> ⚠️ **Runtime Gate Warning**: Abnormal container runtime termination (`execution_status={exec_status}`).\n"
        else:
            return f"> ⚠️ **运行门控警示 (Runtime Gate Warning)**: 容器运行时异常中断 (`execution_status={exec_status}`).\n"
    return None


def _render_evidence_file_pointers(
    evidence: Dict[str, Any],
    lang: str = "bilingual",
    output_format: str = "both",
) -> List[str]:
    artifacts = evidence.get("artifacts") or []
    art_map = {a.get("rel_path"): a for a in artifacts if a.get("rel_path")}

    trial_name = evidence.get("trial_name") or (
        Path(evidence.get("trial_dir")).name if evidence.get("trial_dir") else "trial"
    )
    case_id = evidence.get("case_id") or "case"
    task_dir = evidence.get("task_dir")
    task_name = Path(task_dir).name if task_dir and task_dir != "N/A" else "N/A"

    lines: List[str] = []
    if lang == "zh":
        lines.append("\n### 证据链来源文件索引")
        lines.append(f"- **用例与试次标识**: `case`=`{case_id}`, `trial`=`{trial_name}`, `task`=`{task_name}`")
    elif lang == "en":
        lines.append("\n### Evidence File Pointers")
        lines.append(f"- **Case & Trial Context**: `case`=`{case_id}`, `trial`=`{trial_name}`, `task`=`{task_name}`")
    else:  # bilingual
        lines.append("\n### 证据链来源文件索引 (Evidence File Pointers)")
        lines.append(f"- **用例与试次标识 (Case & Trial Context)**: `case`=`{case_id}`, `trial`=`{trial_name}`, `task`=`{task_name}`")

    # 1. Trajectory
    traj = art_map.get("agent/trajectory.json")
    cc = art_map.get("agent/claude-code.txt")
    # 2. Verifier
    vlog = art_map.get("verifier/verify.log")
    vout = art_map.get("verifier/test-stdout.txt")
    # 3. Task
    inst = art_map.get("instruction.md")
    refs = art_map.get("tests/refs.json") or art_map.get("refs.json")
    # 4. Results
    res_json = art_map.get("results.json")

    has_traj = bool((traj and traj.get("exists")) or (cc and cc.get("exists")))
    has_vlog = bool((vlog and vlog.get("exists")) or (vout and vout.get("exists")))
    has_task = bool((inst and inst.get("exists")) or (refs and refs.get("exists")))
    has_results = bool(res_json and res_json.get("exists"))

    # When all key logs/artifacts are missing, summarize in a single line
    if not has_traj and not has_vlog and not has_task and not has_results:
        if lang == "zh":
            lines.append("- **核心日志与产物**: 全部缺失（未检测到交互轨迹、评测日志、任务说明或计算产物）。")
        elif lang == "en":
            lines.append("- **Core Logs & Artifacts**: All missing (no trajectory, verifier log, task specification, or simulation results found).")
        else:
            lines.append("- **核心日志与产物 (Core Logs & Artifacts)**: 全部缺失 / All missing (未检测到交互轨迹、评测日志、任务说明或计算产物).")
    else:
        # Trajectory
        traj_items = []
        if traj and traj.get("exists"):
            desc = "交互轨迹及工具调用" if lang == "zh" else ("turns & tool calls" if lang == "en" else "交互轨迹及工具调用 / Turns & Tools")
            traj_items.append(f"[trial] `agent/trajectory.json` ({desc})")
        elif traj:
            m_tag = "【缺失】" if lang == "zh" else ("[Missing]" if lang == "en" else "【缺失 / Missing】")
            traj_items.append(f"[trial] `agent/trajectory.json` {m_tag}")

        if cc and cc.get("exists"):
            desc = "执行日志" if lang == "zh" else ("execution log" if lang == "en" else "执行日志 / Execution Log")
            traj_items.append(f"[trial] `agent/claude-code.txt` ({desc})")
        elif cc and not traj:
            m_tag = "【缺失】" if lang == "zh" else ("[Missing]" if lang == "en" else "【缺失 / Missing】")
            traj_items.append(f"[trial] `agent/claude-code.txt` {m_tag}")

        label = "交互轨迹与代码记录" if lang == "zh" else ("Agent Trajectory & Commands" if lang == "en" else "交互轨迹与代码记录 (Agent Trajectory)")
        if traj_items:
            lines.append(f"- **{label}**: " + ", ".join(traj_items))
        else:
            m_tag = "【缺失】" if lang == "zh" else ("[Missing]" if lang == "en" else "【缺失 / Missing】")
            lines.append(f"- **{label}**: [trial] `agent/trajectory.json` {m_tag}")

        # Verifier
        v_items = []
        if vlog and vlog.get("exists"):
            desc = "评测判定日志" if lang == "zh" else ("judgment log" if lang == "en" else "评测判定日志 / Judgment Log")
            v_items.append(f"[trial] `verifier/verify.log` ({desc})")
        elif vlog:
            m_tag = "【缺失】" if lang == "zh" else ("[Missing]" if lang == "en" else "【缺失 / Missing】")
            v_items.append(f"[trial] `verifier/verify.log` {m_tag}")

        if vout and vout.get("exists"):
            desc = "测试输出" if lang == "zh" else ("test stdout" if lang == "en" else "测试输出 / Test Stdout")
            v_items.append(f"[trial] `verifier/test-stdout.txt` ({desc})")
        elif vout and not vlog:
            m_tag = "【缺失】" if lang == "zh" else ("[Missing]" if lang == "en" else "【缺失 / Missing】")
            v_items.append(f"[trial] `verifier/test-stdout.txt` {m_tag}")

        label = "验证器执行与判定日志" if lang == "zh" else ("Verifier Execution & Judgment" if lang == "en" else "验证器执行与判定日志 (Verifier Logs)")
        if v_items:
            lines.append(f"- **{label}**: " + ", ".join(v_items))
        else:
            m_tag = "【缺失】" if lang == "zh" else ("[Missing]" if lang == "en" else "【缺失 / Missing】")
            lines.append(f"- **{label}**: [trial] `verifier/verify.log` {m_tag}")

        # Task
        t_items = []
        if inst and inst.get("exists"):
            desc = "题目要求" if lang == "zh" else ("task prompt" if lang == "en" else "题目要求 / Task Specification")
            t_items.append(f"[task] `instruction.md` ({desc})")
        elif inst:
            m_tag = "【缺失】" if lang == "zh" else ("[Missing]" if lang == "en" else "【缺失 / Missing】")
            t_items.append(f"[task] `instruction.md` {m_tag}")

        if refs and refs.get("exists"):
            desc = "参考真值" if lang == "zh" else ("ground truth" if lang == "en" else "参考真值 / Ground Truth")
            t_items.append(f"[task] `tests/refs.json` ({desc})")
        elif refs:
            m_tag = "【缺失】" if lang == "zh" else ("[Missing]" if lang == "en" else "【缺失 / Missing】")
            t_items.append(f"[task] `tests/refs.json` {m_tag}")

        label = "任务定义与参考真值" if lang == "zh" else ("Task Specification & Reference Values" if lang == "en" else "任务定义与参考真值 (Task Specification)")
        if t_items:
            lines.append(f"- **{label}**: " + ", ".join(t_items))
        else:
            m_tag = "【缺失】" if lang == "zh" else ("[Missing]" if lang == "en" else "【缺失 / Missing】")
            lines.append(f"- **{label}**: [task] `instruction.md` {m_tag}")

        # Results
        if res_json:
            label = "计算产物提交" if lang == "zh" else ("Simulation Output Submission" if lang == "en" else "计算产物提交 (Result Artifacts)")
            if res_json.get("exists"):
                desc = "Agent 最终生成数据" if lang == "zh" else ("simulation output" if lang == "en" else "Agent 最终生成数据 / Output Data")
                lines.append(f"- **{label}**: [trial] `results.json` ({desc})")
            else:
                m_tag = "【缺失】(未生成有效产物)" if lang == "zh" else ("[Missing] (no output generated)" if lang == "en" else "【缺失 / Missing】(未生成有效产物)")
                lines.append(f"- **{label}**: [trial] `results.json` {m_tag}")

    # Output format
    if output_format in ("json", "both"):
        if lang == "zh":
            lines.append("- **全量因果证据矩阵**: 参见 `evidence.json` 与 `analysis.json`（含完整时间线、契约比对及归因推导）\n")
        elif lang == "en":
            lines.append("- **Unified Evidence Matrix**: See `evidence.json` and `analysis.json` (chronological timeline, contract observations, and attribution derivation)\n")
        else:
            lines.append("- **全量因果证据矩阵 (Unified Evidence Matrix)**: 参见 `evidence.json` 与 `analysis.json` (含完整时间线、契约比对及归因推导 / Full timeline & contracts)\n")
    else:
        if lang == "zh":
            lines.append("- **结构化归因产物**: 本次按 `--format markdown` 渲染，未生成独立的 `evidence.json` / `analysis.json`。\n")
        elif lang == "en":
            lines.append("- **Structured Analysis Artifacts**: Rendered with `--format markdown`; `evidence.json` / `analysis.json` were not written.\n")
        else:
            lines.append("- **结构化归因产物 (Structured Artifacts)**: 本次按 `--format markdown` 渲染，未生成独立的 `evidence.json` / `analysis.json`。\n")

    return lines


def _render_chinese_bilingual_core(
    evidence: Dict[str, Any],
    analysis: Dict[str, Any],
    include_en_labels: bool = True,
    output_format: str = "both",
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

    cat = prc.get("category", "unknown")
    subtype = prc.get("subtype", "unknown")
    code = prc.get("code", "UNKNOWN")
    cat_zh = CATEGORY_LABELS_ZH.get(cat, cat)

    lines: List[str] = []
    if include_en_labels:
        lines.append(
            f"# Case Failure Analysis Report / 案例失败因果审计报告: `{case_id}` (`{trial_name}`)\n"
        )
        lines.append(
            "> **Language / 语言版本**: 中英双语对照版 (Bilingual Edition)\n"
        )
    else:
        lines.append(f"# 案例失败因果审计报告: `{case_id}` (`{trial_name}`)\n")

    # 1. 诊断结论与运行态概览
    sec1_title = (
        "## 1. 诊断结论与运行态概览 (Verdict & Root Cause Summary)\n"
        if include_en_labels
        else "## 1. 诊断结论与运行态概览\n"
    )
    lines.append(sec1_title)

    if isinstance(manifestation, dict):
        direct_cause = manifestation.get("summary") or "N/A"
    elif isinstance(manifestation, str):
        direct_cause = manifestation
    else:
        direct_cause = "N/A"

    prc_summary = prc.get("summary") or prc.get("reasoning") if isinstance(prc, dict) else None
    internal_cause = prc_summary or direct_cause or "N/A"

    if include_en_labels:
        lines.append(
            "| 诊断维度 (Dimension) | 判定详情 (Details) |\n"
            "|---|---|\n"
            f"| **最终裁定 (Verdict)** | `{verdict}` (Execution: `{exec_status}`, Verification: `{runtime.get('verification_status', 'unknown')}`, Reward: `{runtime.get('reward')}`) |\n"
            f"| **根因归属 (Root Cause)** | {cat_zh} ➔ `{subtype}` (`{code}`) |\n"
            f"| **阶段跃迁 (Stage Transition)** | 发生阶段 `{f_stage}` ➔ 检出阶段 `{d_stage}` (`{runtime.get('started_at') or '-'}` ~ `{runtime.get('finished_at') or '-'}`) |\n"
            f"| **证据置信度 (Confidence)** | **{conf_val:.2f}** [`{conf_kind}`, strength=`{ev_strength}`] |\n"
        )
    else:
        lines.append(
            "| 诊断维度 | 判定详情 |\n"
            "|---|---|\n"
            f"| **最终裁定** | `{verdict}`（执行状态: `{exec_status}`，验证状态: `{runtime.get('verification_status', 'unknown')}`，得分: `{runtime.get('reward')}`） |\n"
            f"| **根因归属** | 【大类】{cat_zh} ➔ 【二级子类】`{subtype}` (`{code}`) |\n"
            f"| **阶段跃迁** | 发生阶段 `{f_stage}` ➔ 检出阶段 `{d_stage}`（`{runtime.get('started_at') or '-'}` ~ `{runtime.get('finished_at') or '-'}`） |\n"
            f"| **证据置信度** | **{conf_val:.2f}** [`{conf_kind}`，强度=`{ev_strength}`] |\n"
        )

    gate_warn = _render_gate_warning(
        runtime, verdict=verdict, lang="bilingual" if include_en_labels else "zh"
    )
    if gate_warn:
        lines.append(gate_warn)

    if include_en_labels:
        lines.append(
            f"> 🎯 **直接失败表象 (Direct Failure Cause)**: {direct_cause}  \n"
            f"> 🔍 **深层内部根因 (Internal Root Cause)**: {internal_cause}\n"
        )
    else:
        lines.append(
            f"> 🎯 **具体失败表象**: {direct_cause}  \n"
            f"> 🔍 **深层内部根因**: {internal_cause}\n"
        )

    # 2. 故障现场与因果证据链
    sec2_title = (
        "## 2. 故障现场与因果证据链 (Failure Manifestation & Evidence Chain)\n"
        if include_en_labels
        else "## 2. 故障现场与因果证据链\n"
    )
    lines.append(sec2_title)

    fail_snippets = []
    for vobs in evidence.get("verifier_observations") or []:
        if vobs.get("type") == "verifier_fail_message" and (vobs.get("matched_text") or "").strip():
            fail_snippets.append(vobs.get("matched_text", "").strip())
    if fail_snippets:
        lines.append(
            "- **关键失败报错摘要 (Key Failure Message Summary)**:"
            if include_en_labels
            else "- **关键失败报错摘要**:"
        )
        lines.append("```text")
        for snip in fail_snippets[:3]:
            lines.append(snip)
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
    lines.append(
        "- **核心证据引用代号 (`evidence_refs`)**: " + ", ".join(f"`{r}`" for r in ev_refs)
    )

    lines.extend(
        _render_evidence_file_pointers(
            evidence,
            lang="bilingual" if include_en_labels else "zh",
            output_format=output_format,
        )
    )

    # 3. 竞争假设裁决与伴随信号
    sec3_title = (
        "## 3. 竞争假设裁决与伴随信号 (Hypothesis Audit & Signals)\n"
        if include_en_labels
        else "## 3. 竞争假设裁决与伴随信号\n"
    )
    lines.append(sec3_title)
    comp_hyps_raw = analysis.get("competing_hypotheses") or []
    ex_hyps_raw = analysis.get("excluded_hypotheses") or []
    runtime = evidence.get("runtime") or {}
    prc_cat = (analysis.get("primary_root_cause") or {}).get("category", "")
    comp_hyps, ex_hyps = _prune_hypotheses_for_report(
        comp_hyps_raw, ex_hyps_raw, runtime, prc_cat
    )
    for ch in comp_hyps:
        hid = ch.get("hypothesis_id", "H")
        cat_h = ch.get("category", "")
        subtype_h = ch.get("subtype", "")
        score = float(ch.get("confidence", 0.0))
        claim = ch.get("claim", "")
        ev_text = format_evidence_list_text(
            ch.get("evidence_for"),
            ch.get("evidence_against"),
            lang="bilingual" if include_en_labels else "zh",
        )
        if include_en_labels:
            lines.append(
                f"- **候选假设 `{hid}` (`{cat_h}` / `{subtype_h}`, Score: `{score:.2f}`)**: {claim}{ev_text}"
            )
        else:
            lines.append(
                f"- **候选假设 `{hid}` (`{cat_h}` / `{subtype_h}`, 得分: `{score:.2f}`)**: {claim}{ev_text}"
            )

    for eh in ex_hyps:
        if include_en_labels:
            lines.append(
                f"- **排除假设 (Excluded `{eh.get('hypothesis_id', 'H')}`) (`{eh.get('category')}`)**: {eh.get('reason')}"
            )
        else:
            lines.append(
                f"- **排除假设 `{eh.get('hypothesis_id', 'H')}` (`{eh.get('category')}`)**: {eh.get('reason')}"
            )

    if not comp_hyps and not ex_hyps:
        lines.append(
            "- 用例已通过验证，无竞争性失败假设 / Case passed; no competing hypotheses."
            if include_en_labels
            else "- 用例已通过验证，无竞争性失败假设。"
        )

    cfs = analysis.get("contributing_factors") or []
    for cf in cfs:
        cf_cat = cf.get("category")
        cf_code = cf.get("code")
        cf_score = float(cf.get("confidence", 0.0))
        cf_summary = cf.get("summary")
        if include_en_labels:
            lines.append(
                f"- **伴随因素 (Contributing Factor `{cf_cat}` / `{cf_code}`, Score: `{cf_score:.2f}`)**: {cf_summary}"
            )
        else:
            lines.append(
                f"- **伴随因素 (`{cf_cat}` / `{cf_code}`, 置信度: `{cf_score:.2f}`)**: {cf_summary}"
            )

    sigs = evidence.get("behavioral_signals") or []
    if sigs:
        if include_en_labels:
            lines.append(
                f"- **行为信号记录 (Behavioral Signals)**: 共检测到 {len(sigs)} 项潜在行为信号（详细事件见 `evidence.json` 的 `behavioral_signals` / Total {len(sigs)} logged）"
            )
        else:
            lines.append(
                f"- **行为信号记录**: 共检测到 {len(sigs)} 项潜在行为信号（详细事件见 `evidence.json` 的 `behavioral_signals`）"
            )
    lines.append("")

    # 4. 修复行动与处方建议
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
        lines.append(
            "- 无需修复（用例已通过验证） / No remediation required (case passed)."
            if include_en_labels
            else "- 无需修复（用例已通过验证）。"
        )

    sp = analysis.get("skill_prescription")
    if sp and isinstance(sp, dict):
        rec_skill = sp.get("recommended_skill") or sp
        name = rec_skill.get("name")
        gap_str = ", ".join(rec_skill.get("capability_gap") or [])
        if include_en_labels:
            lines.append(
                f"- **领域 Skill 处方 (Domain Skill Prescription `skill-prescription.md`)**: "
                f"建议新增/更新技能 `{name}` (Capability Gap: {gap_str})"
            )
        else:
            lines.append(
                f"- **领域 Skill 处方 (`skill-prescription.md`)**: "
                f"建议新增/更新技能 `{name}`（能力缺口: {gap_str}）"
            )

    missing = evidence.get("missing_artifacts") or []
    if missing:
        core_missing, secondary_cnt = filter_core_missing_artifacts(missing)
        if core_missing:
            core_str = ", ".join(f"`{m}`" for m in core_missing)
            if secondary_cnt > 0:
                if include_en_labels:
                    lines.append(
                        f"- **核心缺失产物 (Missing Core Artifacts `missing_artifacts`)**: {core_str} "
                        f"(已收敛 {secondary_cnt} 项次要临时文件 / {secondary_cnt} secondary files omitted)"
                    )
                else:
                    lines.append(
                        f"- **核心缺失产物 (`missing_artifacts`)**: {core_str} "
                        f"（已收敛 {secondary_cnt} 项次要运行态临时文件）"
                    )
            else:
                if include_en_labels:
                    lines.append(f"- **缺失产物 (Missing Artifacts `missing_artifacts`)**: {core_str}")
                else:
                    lines.append(f"- **缺失产物 (`missing_artifacts`)**: {core_str}")
        elif secondary_cnt > 0:
            if include_en_labels:
                lines.append(
                    f"- **产物完整性 (Artifact Integrity)**: 核心输入与计算产物完整（已收敛 {secondary_cnt} 项次要临时文件 / Core artifacts intact, {secondary_cnt} secondary files omitted）."
                )
            else:
                lines.append(
                    f"- **产物完整性**: 核心输入与计算产物完整（已收敛 {secondary_cnt} 项次要运行态临时文件）。"
                )
    lines.append("")

    return "\n".join(lines)


def _render_english_edition(
    evidence: Dict[str, Any],
    analysis: Dict[str, Any],
    output_format: str = "both",
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
    lines.append(f"# Case Failure Analysis Report: `{case_id}` (`{trial_name}`)\n")

    cat = prc.get("category", "unknown")
    subtype = prc.get("subtype", "unknown")
    code = prc.get("code", "UNKNOWN")
    cat_en = CATEGORY_LABELS_EN.get(cat, cat)

    # 1. Verdict & Root Cause Summary
    lines.append("## 1. Verdict & Root Cause Summary\n")
    if isinstance(manifestation, dict):
        direct_cause = manifestation.get("summary") or "N/A"
    elif isinstance(manifestation, str):
        direct_cause = manifestation
    else:
        direct_cause = "N/A"

    prc_summary = prc.get("summary") or prc.get("reasoning") if isinstance(prc, dict) else None
    internal_cause = prc_summary or direct_cause or "N/A"
    lines.append(
        "| Dimension | Details |\n"
        "|---|---|\n"
        f"| **Verdict** | `{verdict}` (Execution: `{exec_status}`, Verification: `{runtime.get('verification_status', 'unknown')}`, Reward: `{runtime.get('reward')}`) |\n"
        f"| **Root Cause Hierarchy** | [Category] {cat_en} (`{cat}`) ➔ [Subcategory] `{subtype}` (`{code}`) |\n"
        f"| **Stage Transition** | Stage `{f_stage}` → detected at `{d_stage}` (`{runtime.get('started_at') or '-'}` ~ `{runtime.get('finished_at') or '-'}`) |\n"
        f"| **Evidence Confidence** | **{conf_val:.2f}** [`{conf_kind}`, strength=`{ev_strength}`] |\n"
    )

    gate_warn = _render_gate_warning(runtime, verdict=verdict, lang="en")
    if gate_warn:
        lines.append(gate_warn)

    lines.append(
        f"> 🎯 **Direct Failure Cause**: {direct_cause}  \n"
        f"> 🔍 **Internal Root Cause**: {internal_cause}\n"
    )

    # 2. Failure Manifestation & Evidence Chain
    lines.append("## 2. Failure Manifestation & Evidence Chain\n")
    fail_snippets = []
    for vobs in evidence.get("verifier_observations") or []:
        if vobs.get("type") == "verifier_fail_message" and (vobs.get("matched_text") or "").strip():
            fail_snippets.append(vobs.get("matched_text", "").strip())
    if fail_snippets:
        lines.append("- **Key Failure Message Summary**:")
        lines.append("```text")
        for snip in fail_snippets[:3]:
            lines.append(snip)
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
    lines.append(
        "- **Evidence References (`evidence_refs`)**: " + ", ".join(f"`{r}`" for r in ev_refs)
    )

    lines.extend(_render_evidence_file_pointers(evidence, lang="en", output_format=output_format))

    # 3. Hypothesis Audit & Signals
    lines.append("## 3. Hypothesis Audit & Signals\n")
    comp_hyps_raw = analysis.get("competing_hypotheses") or []
    ex_hyps_raw = analysis.get("excluded_hypotheses") or []
    runtime = evidence.get("runtime") or {}
    prc_cat = (analysis.get("primary_root_cause") or {}).get("category", "")
    comp_hyps, ex_hyps = _prune_hypotheses_for_report(
        comp_hyps_raw, ex_hyps_raw, runtime, prc_cat
    )
    for ch in comp_hyps:
        hid = ch.get("hypothesis_id", "H")
        cat_h = ch.get("category", "")
        subtype_h = ch.get("subtype", "")
        score = float(ch.get("confidence", 0.0))
        claim = ch.get("claim", "")
        ev_text = format_evidence_list_text(
            ch.get("evidence_for"), ch.get("evidence_against"), lang="en"
        )
        lines.append(
            f"- **Candidate `{hid}` (`{cat_h}` / `{subtype_h}`, Score: `{score:.2f}`)**: {claim}{ev_text}"
        )

    for eh in ex_hyps:
        lines.append(
            f"- **Excluded `{eh.get('hypothesis_id')}` (`{eh.get('category')}`)**: {eh.get('reason')}"
        )
    if not comp_hyps and not ex_hyps:
        lines.append("- Case passed; no competing failure hypotheses.")

    for cf in analysis.get("contributing_factors") or []:
        cf_cat = cf.get("category")
        cf_code = cf.get("code")
        cf_score = float(cf.get("confidence", 0.0))
        cf_summary = cf.get("summary")
        lines.append(
            f"- **Contributing Factor (`{cf_cat}` / `{cf_code}`, Confidence: `{cf_score:.2f}`)**: {cf_summary}"
        )

    sigs = evidence.get("behavioral_signals") or []
    if sigs:
        lines.append(
            f"- **Behavioral Signals Logged**: Total {len(sigs)} behavioral signals recorded (see `evidence.json` under `behavioral_signals` for step-by-step details)."
        )
    lines.append("")

    # 4. Recommended Actions & Notes
    lines.append("## 4. Recommended Actions & Notes\n")
    recs = analysis.get("recommended_actions") or []
    if recs:
        for r in recs:
            lines.append(f"- **[{r.get('owner', 'General')}]**: {r.get('action')}")
    else:
        lines.append("- No remediation required (case passed).")

    sp = analysis.get("skill_prescription")
    if sp and isinstance(sp, dict):
        rec_skill = sp.get("recommended_skill") or sp
        name = rec_skill.get("name")
        gap_str = ", ".join(rec_skill.get("capability_gap") or [])
        lines.append(
            f"- **Domain Skill Prescription (`skill-prescription.md`)**: Recommended skill `{name}` "
            f"(Capability Gap: {gap_str})"
        )

    missing = evidence.get("missing_artifacts") or []
    if missing:
        core_missing, secondary_cnt = filter_core_missing_artifacts(missing)
        if core_missing:
            core_str = ", ".join(f"`{m}`" for m in core_missing)
            if secondary_cnt > 0:
                lines.append(
                    f"- **Missing Core Artifacts (`missing_artifacts`)**: {core_str} "
                    f"({secondary_cnt} secondary runtime files omitted)"
                )
            else:
                lines.append(f"- **Missing Artifacts (`missing_artifacts`)**: {core_str}")
        elif secondary_cnt > 0:
            lines.append(
                f"- **Artifact Integrity**: Core inputs and outputs intact "
                f"({secondary_cnt} secondary runtime files omitted)."
            )
    lines.append("")
    return "\n".join(lines)


def _render_passed_edition(
    evidence: Dict[str, Any],
    analysis: Dict[str, Any],
    lang: str = "bilingual",
    output_format: str = "both",
) -> str:
    """
    Renders lightweight passed trial view (< 30 lines):
      - Verdict & Pass Summary (verdict, stage, confidence, pass criteria)
      - Verification Evidence & Artifacts (context, verified existing files, matrix index)
      - Zero failure root cause, failure hypotheses, or missing artifacts clutter.
    """
    case_id = analysis.get("case_id", evidence.get("case_id", "unknown"))
    trial_name = analysis.get("trial_name", evidence.get("trial_name", case_id))
    task_dir = evidence.get("task_dir")
    task_name = Path(task_dir).name if task_dir and task_dir != "N/A" else "N/A"

    lines: List[str] = []

    if lang == "zh":
        lines.append(f"# 评测诊断报告: `{case_id}` / `{trial_name}`\n\n")
        lines.append("> 语言版本: 简体中文 (Chinese Edition)\n\n")
        lines.append("## 1. 评测裁定与通过概览\n\n")
        lines.append(
            "| 诊断维度 | 判定结果 |\n"
            "|---|---|\n"
            "| **最终裁定** | `passed` |\n"
            "| **执行阶段** | `passed` |\n"
            "| **置信度** | 1.00 |\n\n"
        )
        lines.append(
            "> ✅ **通过依据**: 用例评测规则全部通过，未检测到未恢复异常或规格违规。\n\n"
        )
        lines.append("## 2. 验证证据与产物索引\n\n")
        lines.append(
            f"- **用例与试次标识**: `case`=`{case_id}`, `trial`=`{trial_name}`, `task`=`{task_name}`\n"
        )
    elif lang == "en":
        lines.append(f"# Case Execution Report: `{case_id}` / `{trial_name}`\n\n")
        lines.append("> Language: English Edition\n\n")
        lines.append("## 1. Verdict & Pass Summary\n\n")
        lines.append(
            "| Dimension | Result |\n"
            "|---|---|\n"
            "| **Verdict** | `passed` |\n"
            "| **Execution Stage** | `passed` |\n"
            "| **Confidence** | 1.00 |\n\n"
        )
        lines.append(
            "> ✅ **Pass Criteria**: Evaluation rules fully satisfied; no unrecovered runtime or specification deviations detected.\n\n"
        )
        lines.append("## 2. Verification Evidence & Artifacts\n\n")
        lines.append(
            f"- **Case & Trial Context**: `case`=`{case_id}`, `trial`=`{trial_name}`, `task`=`{task_name}`\n"
        )
    else:  # bilingual
        lines.append(f"# Case Execution Report / 评测诊断报告: `{case_id}` / `{trial_name}`\n\n")
        lines.append("> **Language / 语言版本**: 中英双语对照版 (Bilingual Edition)\n\n")
        lines.append("## 1. 评测裁定与通过概览 (Verdict & Pass Summary)\n\n")
        lines.append(
            "| 诊断维度 (Dimension) | 判定结果 (Result) |\n"
            "|---|---|\n"
            "| **最终裁定 (Verdict)** | `passed` |\n"
            "| **执行阶段 (Stage)** | `passed` |\n"
            "| **置信度 (Confidence)** | 1.00 |\n\n"
        )
        lines.append(
            "> ✅ **通过依据 (Pass Criteria)**: 用例评测规则全部通过，未检测到未恢复异常或规格违规 "
            "(Evaluation rules fully satisfied; no unrecovered runtime or specification deviations detected).\n\n"
        )
        lines.append("## 2. 验证证据与产物索引 (Verification Evidence & Artifacts)\n\n")
        lines.append(
            f"- **用例与试次标识 (Case & Trial Context)**: `case`=`{case_id}`, `trial`=`{trial_name}`, `task`=`{task_name}`\n"
        )

    # Existing verified artifacts
    artifacts = evidence.get("artifacts") or []
    existing = [a.get("rel_path") for a in artifacts if a.get("exists") and a.get("rel_path")]
    if existing:
        art_items = ", ".join(f"`{p}`" for p in existing)
        if lang == "zh":
            lines.append(f"- **已验证产物记录**: {art_items}\n")
        elif lang == "en":
            lines.append(f"- **Verified Artifacts**: {art_items}\n")
        else:
            lines.append(f"- **已验证产物记录 (Verified Artifacts)**: {art_items}\n")
    else:
        if lang == "zh":
            lines.append("- **已验证产物记录**: 评测规则判定通过（无额外文件产物记录）。\n")
        elif lang == "en":
            lines.append("- **Verified Artifacts**: Passed with no additional artifact records.\n")
        else:
            lines.append("- **已验证产物记录 (Verified Artifacts)**: 评测规则判定通过 / Passed with no extra artifacts.\n")

    # Output format note / Evidence matrix link
    if output_format in ("json", "both"):
        if lang == "zh":
            lines.append("- **全量验证矩阵**: 详见 `evidence.json` 与 `analysis.json`。\n")
        elif lang == "en":
            lines.append("- **Verification Matrix**: See `evidence.json` and `analysis.json`。\n")
        else:
            lines.append("- **全量验证矩阵 (Verification Matrix)**: 详见 `evidence.json` 与 `analysis.json`。\n")
    else:
        if lang == "zh":
            lines.append("- **结构化归因产物**: 本次按 `--format markdown` 渲染。\n")
        elif lang == "en":
            lines.append("- **Structured Analysis Artifacts**: Rendered with `--format markdown`.\n")
        else:
            lines.append("- **结构化归因产物 (Structured Artifacts)**: 本次按 `--format markdown` 渲染。\n")

    return "".join(lines)


def render_report_markdown(
    evidence: Dict[str, Any],
    analysis: Dict[str, Any],
    lang: str = "bilingual",
    output_format: str = "both",
) -> str:
    """
    Renders report markdown:
      - For passed trials: lightweight 2-section view (< 30 lines) without failure semantics
      - `lang="zh"`: Standalone pure Chinese report
      - `lang="en"`: Standalone pure English report
      - `lang="bilingual"`: Compact bilingual edition with parallel bilingual labels (no duplicated Part II)
    """
    verdict = analysis.get("verdict", "failed")
    if verdict == "passed":
        return _render_passed_edition(
            evidence, analysis, lang=lang, output_format=output_format
        )

    if lang == "en":
        return _render_english_edition(
            evidence, analysis, output_format=output_format
        )
    if lang == "zh":
        return _render_chinese_bilingual_core(
            evidence, analysis, include_en_labels=False, output_format=output_format
        )

    # Default `bilingual`: Compact Chinese-English bilingual labeled edition (4 core sections).
    return _render_chinese_bilingual_core(
        evidence, analysis, include_en_labels=True, output_format=output_format
    )


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
            "- **核心执行指引 (`required_guidance`)**: "
            + "；".join(rec.get("required_guidance") or []),
            "- **禁止的反模式 (`anti_patterns`)**: " + "；".join(rec.get("anti_patterns") or []),
            "",
        ]
    )

    en_section = "\n".join(
        [
            f"- **Recommended Skill Name**: `{name}`",
            "- **Trigger Conditions (`trigger`)**: " + "; ".join(rec.get("trigger") or []),
            "- **Capability Gap (`capability_gap`)**: "
            + "; ".join(rec.get("capability_gap") or []),
            "- **Required Guidance (`required_guidance`)**: "
            + "; ".join(rec.get("required_guidance") or []),
            "- **Anti-Patterns to Avoid (`anti_patterns`)**: "
            + "; ".join(rec.get("anti_patterns") or []),
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

    parser = argparse.ArgumentParser(
        description="Render bilingual report.md and optional skill-prescription.md."
    )
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
