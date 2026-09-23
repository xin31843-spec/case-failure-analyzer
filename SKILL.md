---
name: case-failure-analyzer
description: Analyze failed scientific-computing benchmark cases from job artifacts, agent trajectories, task definitions, and verifier code; attribute failures to case specification, infrastructure, agent behavior, scientific decisions, verifier defects, or numerical nondeterminism. Output bilingual (Chinese & English) causal audit reports.
metadata:
  short-description: Audit scientific benchmark case failures and root causes
---

# Case Failure Analyzer (Scientific Case Failure Analyzer / 科学计算基准用例失败因果分析器)

> **Canonical instructions are English.** The full Chinese specification lives in
> [references/instructions.zh.md](references/instructions.zh.md); a condensed Chinese
> summary is kept in [Part II](#part-ii-中文规范说明-chinese) below.
> **规范以英文为准**；完整中文说明见 [references/instructions.zh.md](references/instructions.zh.md)。

---

## Part I: English Specification

Use this skill when asked to diagnose why a scientific-computing benchmark case (`jobs/<job_name>` + `tasks/<task_name>`) failed.

It performs an end-to-end, evidence-backed causal audit rather than naive log keyword matching:
**Artifact Collection → Unified Runtime State → Timeline Reconstruction → Contract Audit → Scientific Error Diagnosis → Candidate Hypothesis Competition → Causal Attribution → Bilingual Report & Skill Prescription**

### Inputs

Require or discover:
- `--job`: Job directory (`jobs/<job_name>` or `jobs_failed_backup/<job_name>`) or specific trial directory
- `--task`: Corresponding task definition directory (`tasks/<task_name>`)

### Default Behavior & Boundaries

- **Read-only by default**: Never modifies `tasks/`, `jobs/`, or `tests/verify.py`.
- **Deterministic Evidence Extraction + Model Causal Reasoning**: Deterministic scripts extract `evidence.json` and `candidate-hypotheses.json`; the Agent/Codex evaluates competing hypotheses per `references/attribution-protocol.md` (or validates the conservative draft in `analysis.json`).
- **Evidence-first attribution**: Never assigns a root cause from a single keyword match. Separates **failure manifestation (symptom)**, **detection stage**, and **primary root cause**.
- **Positive-evidence gate for Agent blame**: Never defaults to `agent` when other gates do not fire. Requires positive agent evidence (`behavioral_signals`, `agent_mismatch` contract, or agent-caused `scientific_observations`).
- **Calibrated uncertainty**: Outputs `unknown` (`UNKNOWN_INSUFFICIENT_EVIDENCE`) when evidence cannot distinguish competing hypotheses.
- **Bilingual Report Output**: Always produces a Chinese-English bilingual `report.md` (along with standalone `report.zh.md` and `report.en.md`, plus bilingual `skill-prescription.md` when eligible).

### Runtime Contract

- `scripts/analyze_case.py` is the single entrypoint; it is **read-only** unless `--output` is supplied.
- Supported trajectory schemas: `ATIF-v1.7` (primary), plus `ATIF-v1.6` / `ATIF-v1.5`.
- Output schema version: `failure-analysis-v1` (see `references/evidence-schema.md` and `references/report-schema.md`).
- Bilingual output is mandatory for `--phase all`: `report.md`, `report.zh.md`, `report.en.md`, and `skill-prescription.md` only when eligible.
- Invalid inputs (missing `--job`/`--task`, unknown `--trial`, empty job tree without job-level evidence) exit with code `2` and write nothing.

### Workflow

1. **Run Evidence Collection & Candidate Hypothesis Generation**
   Execute `scripts/analyze_case.py` (supports `--phase collect` for evidence + candidate hypotheses, or `--phase all` for end-to-end conservative attribution and bilingual report generation):
   ```bash
   python3 "${CODEX_HOME:-$HOME/.codex}/skills/case-failure-analyzer/scripts/analyze_case.py" \
     --job jobs/<job_name> \
     --task tasks/<task_name> \
     --output failure-analysis/<case_id>
   ```
2. **Gate on Per-Trial Startup & Infrastructure State (`scripts/runtime_state.py` + `scripts/extract_runtime_errors.py`)**
   Determine from `evidence.json` (`runtime.agent_started`, `runtime.verifier_started`, `runtime.execution_status`, `runtime.verification_status`, `error_observations`) whether the trial passed (`reward >= 1.0`) or whether the container/agent failed prior to startup. Job-level `stats.n_errored_trials` is never used to mark an individual passing trial as failed.
3. **Reconstruct the Unified Execution Timeline**
   Trace chronological events across runner setup, agent steps (`ATIF-v1.7`), tool calls, file writes, and verifier execution.
4. **Audit the Three-Way Contract (`Prompt <-> Verifier <-> Agent Output`)**
   Inspect `contract_observations` and `verifier_observations` (`failure_binding: direct | indirect | none`, `verifier_internal_crash`) from `scripts/audit_contract.py` to distinguish genuine agent contract violations from causally bound verifier parser defects or internal verifier crashes.
5. **Extract Scientific Software Error Events**
   Review `scientific_observations` from `scripts/extract_scientific_errors.py` (backed by the unified registry `references/error-families.json`) and consult `references/software/<software>.md` for discriminating evidence requirements.
6. **Identify the First Unrecovered Deviation (`first_unrecovered_deviation`)**
   Record `{"status": "identified", "event_ref": "...", "summary": "..."}` or `{"status": "not_identified", "event_ref": null, "summary": "..."}` when logs are incomplete.
7. **Evaluate Competing Root-Cause Hypotheses (`candidate-hypotheses.json`)**
   Compare structured hypotheses (`H1`, `H2`, ...) with `evidence_for`, `evidence_against`, `missing_evidence`, `counterfactual_test`, and heuristic evidence scores (`scripts/confidence.py`).
8. **Assign Primary Root Cause & Contributing Factors**
   Select exactly one `primary_root_cause` and zero or more `contributing_factors`.
9. **Validate & Render Bilingual Outputs**
   Validate `evidence.json`, `analysis.json`, and `report.md` via `scripts/validate_analysis.py`, then render bilingual `report.md`, `report.zh.md`, `report.en.md` (and bilingual `skill-prescription.md` only when eligible) via `scripts/render_report.py`.

### Model-in-the-Loop Attribution (optional)

`--phase all` emits a conservative, fully deterministic draft `analysis.json`. To substitute a
model-authored attribution, write or edit `analysis.json` by hand and validate/render it explicitly:

```bash
python3 "${CODEX_HOME:-$HOME/.codex}/skills/case-failure-analyzer/scripts/validate_analysis.py" \
  --evidence failure-analysis/<case_id>/evidence.json \
  --analysis failure-analysis/<case_id>/analysis.json \
  --report  failure-analysis/<case_id>/report.md

python3 "${CODEX_HOME:-$HOME/.codex}/skills/case-failure-analyzer/scripts/render_report.py" \
  --evidence failure-analysis/<case_id>/evidence.json \
  --analysis failure-analysis/<case_id>/analysis.json \
  --output-report failure-analysis/<case_id>/report.md \
  --output-prescription failure-analysis/<case_id>/skill-prescription.md \
  --lang bilingual
```

`validate_analysis.py` enforces every Hard Rule below; a rejected `analysis.json` must be corrected, never rendered.

### Attribution Constraints (Hard Rules)

1. **Do not classify solely from an error string or bare keyword.** A `Connection failed`, `SCF NOT CONVERGED`, or bare `chaotic` string is only causal if supported by structured evidence and unrecovered downstream impact.
2. **Distinguish symptom, detection point, and root cause.** A failure detected in `verifier_execution` (`FAIL: ...`) may be caused by `verifier` (parser defect or internal crash), `case` (ambiguous spec or missing asset), `agent` (wrong calculation), or `numerical` drift.
3. **Pre-startup rule (`runtime.agent_started == false`):**
   - If `runtime.agent_started == false` AND fatal infrastructure evidence exists -> `primary_root_cause.category` MUST be `infra`.
   - If `runtime.agent_started == false` AND no infrastructure/exception logs exist -> `primary_root_cause.category` MUST be `unknown` (`UNKNOWN_INSUFFICIENT_EVIDENCE`).
   - If `runtime.agent_started == false` -> `primary_root_cause.category` is **STRICTLY FORBIDDEN** from being `agent`.
4. **Positive evidence is required for `agent` attribution.** `reward == 0` or `FAIL` in `verify.log` alone is NOT positive agent evidence. At least one positive agent signal (`behavioral_signals`, `agent_mismatch`, agent timeline error, or agent-caused `scientific_observations`) must be cited.
5. **A static verifier hazard must be causally bound (`failure_binding == "direct"`).** An unrelated `1.23D+03` reference number in `verify.log` when the agent wrote `9.99E+02` must NOT trigger `verifier`. Conversely, a verifier internal crash (`FileNotFoundError` on verifier temp/ref paths) MUST be attributed to `verifier` (`VERIFIER_RECOMPUTE_DEFECT`), never `agent`.
6. **Use `unknown` when evidence cannot distinguish competing hypotheses.**
7. **Generate `skill-prescription.md` ONLY for reusable, generalizable agent capability gaps.** Never generate a domain skill to work around an infrastructure failure, case defect, or verifier bug.

---

## Part II: 中文规范说明 (Chinese)

> 完整中文规范（输入参数、默认边界、核心工作流、归因约束全文）见
> [references/instructions.zh.md](references/instructions.zh.md)。
> `SKILL.md` 仅保留英文 canonical 说明与本节摘要，以避免同一规范中英双份重复占用上下文。

本 Skill 端到端诊断科学计算基准用例（`jobs/<job_name>` + `tasks/<task_name>`）的失败原因，产出中英双版因果审计报告（`report.md` / `report.zh.md` / `report.en.md`，以及仅在满足条件时生成的 `skill-prescription.md`）。

归因硬性约束（与 Part I §Attribution Constraints 等价）：

1. **严禁仅凭单一关键词定根因**。
2. **严格区分失败现象、检测阶段与责任根因**。
3. **Agent 未启动硬规则 (`runtime.agent_started == false`)**：存在致命基础设施证据 → 必须归因 `infra`；无任何异常/构建日志证据 → 必须归因 `unknown` (`UNKNOWN_INSUFFICIENT_EVIDENCE`)；**绝对禁止**归因 `agent`。
4. **归因 `agent` 必须具备正面证据**：仅有 `reward=0` 或 `verify.log` 报错不构成 Agent 正面证据。
5. **静态解析 Hazard 必须完成因果绑定 (`failure_binding == "direct"`)**。
6. **证据不足或竞争假设无法区分时必须输出 `unknown`**。
7. **仅针对可复用的 Agent 科学/工程能力缺口生成 `skill-prescription.md`**。

---

## References / 参考文档

Before finalizing complex attributions, consult / 在完成复杂案例归因前请查阅：
- [references/taxonomy.md](references/taxonomy.md)
- [references/attribution-protocol.md](references/attribution-protocol.md)
- [references/evidence-schema.md](references/evidence-schema.md)
- [references/report-schema.md](references/report-schema.md)
- [references/skill-prescription-policy.md](references/skill-prescription-policy.md)
- [references/instructions.zh.md](references/instructions.zh.md) (完整中文规范 / full Chinese specification)
- [references/error-families.json](references/error-families.json)
- Software knowledge bases in `references/software/` (`软件错误知识库`):
  - [cp2k.md](references/software/cp2k.md)
  - [quantum-espresso.md](references/software/quantum-espresso.md)
  - [lammps.md](references/software/lammps.md)
  - [ase.md](references/software/ase.md)
  - [xtb.md](references/software/xtb.md)
  - [rdkit.md](references/software/rdkit.md)
