# Report Schema (`report.md`)

Every generated `report.md` MUST include the following 11 sections in exact order so human reviewers and automated validators (`scripts/validate_analysis.py`) can audit the report consistently.

## Required Sections

1. `## 1. Executive Summary`
   Concise overview of the case verdict, primary root cause (`category` / `code` / `confidence`), failure stage vs detection stage, and one-sentence takeaway.
2. `## 2. Case 状态`
   Table summarizing `case_id`, `trial_name`, `exit_status`, `reward`, `agent_started`, `verifier_started`, and key artifact availability.
3. `## 3. 执行时间线`
   Chronological table of key events from `evidence.json` (`event_id`, `timestamp`, `actor`, `event_type`, `summary`, `source_pointer`), highlighting the **First Unrecovered Deviation (`first_unrecovered_deviation`)**.
4. `## 4. 直接失败现象`
   Exact symptom observed at the detection point (`failure_manifestation.type`, `failure_manifestation.summary`, and verbatim verifier/exception snippet).
5. `## 5. 主根因`
   Detailed causal explanation of `primary_root_cause`, including `category`, `subtype`, `code`, `confidence`, and step-by-step causal mechanism linking the root cause to the final failure.
6. `## 6. 伴随因素`
   List of `contributing_factors` (or explicit statement that no secondary contributing factors were present) and behavioral observations (`behavioral_signals`).
7. `## 7. 证据链`
   Contract Matrix table (`Prompt <-> Verifier <-> Agent Output`) and bulleted list of `evidence_refs` with exact file paths and JSON/line pointers.
8. `## 8. 排除的假设`
   Structured table/list of competing hypotheses (`excluded_hypotheses`) and the objective evidence that falsified or ruled them out (especially why Agent or Verifier was excluded).
9. `## 9. 建议修复责任方`
   Actionable remediation items grouped by owner (`Case`, `Infra`, `Verifier`, `Agent Policy`).
10. `## 10. Skill 处方`
    Either the structured summary of the recommended domain skill (linking to `skill-prescription.md`) OR an explicit explanation of why a Skill Prescription is NOT generated (e.g., root cause is `infra` or `verifier`).
11. `## 11. 缺失证据与分析限制`
    List of `missing_artifacts`, truncated logs, or unverified counterfactuals that bound the confidence of the analysis.
