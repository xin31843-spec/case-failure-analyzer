# Report Schema (`report.md`)

Every generated `report.md` MUST include the following **4 core sections** in exact order with start-of-line headings (`## <N>. <Title>`) and non-empty body text so human reviewers and automated validators (`scripts/validate_analysis.py`) can audit the report consistently without redundant field duplication or empty boilerplate sections.

Every invocation of `scripts/render_report.py` / `scripts/analyze_case.py` generates:
- `report.md`: Unified Chinese-English bilingual report containing Part I (Chinese-English side-by-side with the 4 canonical headers) and Part II (Complete English Edition).
- `report.zh.md`: Standalone Chinese edition (4 core sections).
- `report.en.md`: Standalone English edition (4 core sections).

---

## Required Sections

1. `## 1. 诊断结论与运行态概览` (or `## 1. Verdict & Root Cause Summary`)
   Concise overview of the case verdict and runtime startup gates (`execution_status`, `verification_status`, `reward`, `agent_started`, `verifier_started`), primary root cause (`category` / `subtype` / `code` / `confidence` / `evidence_strength`), failure stage vs detection stage, and causal mechanism (`primary_root_cause.summary`).
2. `## 2. 故障现场与因果证据链` (or `## 2. Failure Manifestation & Evidence Chain`)
   Direct failure manifestation (`failure_manifestation.type`, `summary`, and verbatim verifier snippet), **First Unrecovered Deviation (`first_unrecovered_deviation`)**, resolvable `evidence_refs`, plus dynamically rendered chronological timeline table and Three-Way Contract Matrix (`Prompt <-> Verifier <-> Agent Output`) when non-empty.
3. `## 3. 竞争假设裁决与伴随信号` (or `## 3. Hypothesis Audit & Signals`)
   Structured evaluation of `competing_hypotheses` and `excluded_hypotheses` with supporting/contradicting evidence, plus dynamically rendered `contributing_factors` and objective `behavioral_signals` when present.
4. `## 4. 修复行动与处方建议` (or `## 4. Recommended Actions & Notes`)
   Actionable remediation items grouped by owner (`Case`, `Infra`, `Verifier`, `Agent Policy`), plus optional `skill-prescription.md` summary (only when eligible) and `missing_artifacts` note (only when artifacts are missing).
