# Report Schema (`report.md`) / 报告结构规范 (中英双版)

Every generated `report.md` MUST include the following 11 sections in exact order with start-of-line headings (`## <N>. <Title>`) and non-empty body text so human reviewers and automated validators (`scripts/validate_analysis.py`) can audit the report consistently.
Every invocation of `scripts/render_report.py` / `scripts/analyze_case.py` generates:
- `report.md`: Unified **Chinese-English Bilingual Report (中英双语版)** containing Part I (Chinese-English side-by-side with the 11 canonical headers) and Part II (Complete English Edition).
- `report.zh.md`: Standalone Chinese edition (纯中文版).
- `report.en.md`: Standalone English edition (纯英文版).

---

## Required Sections / 必备的 11 个章节

1. `## 1. Executive Summary`
   Concise bilingual overview of the case verdict (`execution_status`, `verification_status`, `reward`), primary root cause (`category` / `code` / `confidence` / `evidence_strength`), failure stage vs detection stage, and takeaway.
   简要概述最终裁定、主根因、发生阶段与检测阶段、以及核心结论（中英双语）。
2. `## 2. Case 状态` (e.g. `## 2. Case 状态 (Case & Trial Runtime Status)`)
   Table summarizing `case_id`, `trial_name`, `execution_status`, `verification_status`, `exit_status`, `reward`, `agent_started`, `verifier_started`, `started_at`, and `finished_at`.
   汇总单 Trial 运行态与启动门控指标表格。
3. `## 3. 执行时间线` (e.g. `## 3. 执行时间线 (Execution Timeline)`)
   Chronological table of key events from `evidence.json`, always preserving and highlighting the **First Unrecovered Deviation (`first_unrecovered_deviation`)** (`status: identified | not_identified`).
   按时间顺序展示关键轨迹事件表，并突出显示首次不可恢复偏离点。
4. `## 4. 直接失败现象` (e.g. `## 4. 直接失败现象 (Direct Failure Manifestation)`)
   Exact symptom observed at the detection point (`failure_manifestation.type`, `failure_manifestation.summary`, and verbatim verifier/exception snippet).
   记录暴露点观测到的直接失败表象与原始报错摘录。
5. `## 5. 主根因` (e.g. `## 5. 主根因 (Primary Root Cause)`)
   Detailed causal explanation of `primary_root_cause`, including `category`, `subtype`, `code`, `confidence` (`heuristic_evidence_score`), `evidence_strength`, and step-by-step causal mechanism.
   详述唯一主根因分类、证据强度评分与因果传导机制。
6. `## 6. 伴随因素` (e.g. `## 6. 伴随因素 (Contributing Factors & Behavioral Signals)`)
   List of `contributing_factors` and objective `behavioral_signals`.
   列出次要伴随根因及客观行为信号。
7. `## 7. 证据链` (e.g. `## 7. 证据链 (Evidence Chain & Contract Matrix)`)
   Three-Way Contract Matrix table (`Prompt <-> Verifier <-> Agent Output`) and bulleted list of resolvable `evidence_refs`.
   展示三方契约审计矩阵与全部可解析证据引用 ID。
8. `## 8. 排除的假设` (e.g. `## 8. 排除的假设 (Competing & Excluded Hypotheses)`)
   Structured summary of `competing_hypotheses` and `excluded_hypotheses` with supporting/contradicting evidence.
   展示竞争假设评分对比及已排除假设的证伪依据。
9. `## 9. 建议修复责任方` (e.g. `## 9. 建议修复责任方 (Recommended Actions by Owner)`)
   Actionable remediation items grouped by owner (`Case`, `Infra`, `Verifier`, `Agent Policy`).
   按责任方分类给出具体修复动作建议。
10. `## 10. Skill 处方` (e.g. `## 10. Skill 处方 (Domain Skill Prescription)`)
    Structured summary linking to bilingual `skill-prescription.md` OR explicit policy rationale for why no domain skill is generated.
    给出领域技能处方摘要，或依据策略说明为何不生成领域 Skill。
11. `## 11. 缺失证据与分析限制` (e.g. `## 11. 缺失证据与分析限制 (Missing Evidence & Analysis Limitations)`)
    List of `missing_artifacts` and static analysis boundaries.
    列出缺失产物文件与静态取证分析边界。
