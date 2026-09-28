# Report Schema (`report.md`)

**[English](report-schema.md) | [简体中文](../zh/report-schema.md)**

Every generated `report.md` MUST include the following **4 high-signal core sections** in exact order with start-of-line headings (`## <N>. <Title>`) and non-empty body text. This structure eliminates redundant field duplication and empty placeholder noise while preserving the full causal audit trail validated by `scripts/validate_analysis.py`.

Every invocation of `scripts/render_report.py` / `scripts/analyze_case.py` generates:
- `report.md`: Unified Chinese-English bilingual report containing Part I (Chinese-English side-by-side with the 4 canonical headers) and Part II (Complete English Edition).
- `report.zh.md`: Standalone Chinese edition (4 core sections).
- `report.en.md`: Standalone English edition (4 core sections).

---

## Required 4 Core Sections

1. `## 1. 诊断结论与运行态概览` (or `## 1. Verdict & Root Cause Summary`)
   - **Consolidates Executive Summary + Runtime Status + Primary Root Cause**: Summarizes the trial verdict and startup gates (`verdict`, `execution_status`, `verification_status`, `reward`, `agent_started`, `verifier_started`), the single `primary_root_cause` (`category` / `subtype` / `code` / `confidence` / `evidence_strength`), `failure_stage -> detection_stage` transition, and the step-by-step causal mechanism (`primary_root_cause.summary`).
2. `## 2. 故障现场与因果证据链` (or `## 2. Failure Manifestation & Evidence Chain`)
   - **Consolidates Direct Failure Manifestation + Deviation/Timeline + Contract Matrix/Evidence Refs**:
     - Direct symptom at the detection point (`failure_manifestation.type`, `summary`, and verbatim verifier failure snippet);
     - **First Unrecovered Deviation (`first_unrecovered_deviation`)** and resolvable `evidence_refs`;
     - **Dynamic folding**: Renders the chronological timeline table only when trajectory events exist, and renders the Three-Way Contract Matrix (`Prompt <-> Verifier <-> Agent Output`) only when contract observations are present.
3. `## 3. 竞争假设裁决与伴随信号` (or `## 3. Hypothesis Audit & Signals`)
   - **Consolidates Competing/Excluded Hypotheses + Contributing Factors/Behavioral Signals**:
     - Structured evaluation of `competing_hypotheses` and `excluded_hypotheses` with supporting/contradicting evidence;
     - **Dynamic folding**: Appends `contributing_factors` and objective `behavioral_signals` only when non-empty.
4. `## 4. 修复行动与处方建议` (or `## 4. Recommended Actions & Notes`)
   - **Consolidates Recommended Actions + Optional Skill Prescription + Optional Missing Artifacts**:
     - Actionable remediation items grouped by owner (`Case`, `Infra`, `Verifier`, `Agent Policy`);
     - **Dynamic folding**: Includes the `skill-prescription.md` summary only when eligible (`primary_root_cause.category == "agent"` with a reusable capability gap), and lists `missing_artifacts` only when artifacts are absent.
