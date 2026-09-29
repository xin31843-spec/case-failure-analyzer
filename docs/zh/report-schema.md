# Report Schema (`report.md`)

Every generated `report.md` MUST include the following **4 core sections** in exact order with start-of-line headings (`## <N>. <Title>`) and non-empty body text so human reviewers and automated validators (`scripts/validate_analysis.py`) can audit the report consistently.

Following user and reviewer experience principles, reports adhere to the **Concise & Direct (简洁直观)** standard:
- **直击痛点**：直接点明具体直接失败原因（表面现象），并深入剖析更具体的内部深层物理/工程根因。
- **证据解耦**：不再在 Markdown 报告中平铺几十行的时间线大表格和行为信号日志，而是提供清晰精确的 **证据链文件索引 (Evidence File Pointers)**，指明在 `agent/trajectory.json`、`verifier/verify.log`、`evidence.json` 等哪些具体文件中查看完整证据。

Every invocation of `scripts/render_report.py` / `scripts/analyze_case.py` generates:
- `report.md`: Unified Chinese-English bilingual report containing Part I (Chinese-English side-by-side with the 4 canonical headers) and Part II (Complete English Edition).
- `report.zh.md`: Standalone Chinese edition (4 core sections).
- `report.en.md`: Standalone English edition (4 core sections).

---

## Required Sections

1. `## 1. 诊断结论与运行态概览` (or `## 1. Verdict & Root Cause Summary`)
   - 裁定与运行门控 (`verdict`, `execution_status`, `verification_status`, `reward`, `agent_started`, `verifier_started`).
   - 唯一主根因 (`category` / `subtype` / `code` / `confidence`).
   - 阶段跃迁 (`failure_stage` → `detection_stage`).
   - **具体失败原因 (Direct Cause)**：直接点明任务在表面上因何失败（如验证器报什么错误，缺少什么交付物）。
   - **深层内部根因 (Internal Root Cause)**：阐明内部深层机理（如数学范数理解偏差、未开自旋极化、容差过紧超差等）。

2. `## 2. 故障现场与因果证据链` (or `## 2. Failure Manifestation & Evidence Chain`)
   - 关键失败报错摘要（精简提取 1~3 行关键判分日志）。
   - 首次不可恢复偏离点 (`first_unrecovered_deviation`：发生时间、偏离动作与原因说明）。
   - 核心证据引用代号 (`evidence_refs`)。
   - **证据链来源文件索引 (Evidence File Pointers)**：明确指引在何处查看完整证据链，包括：
     - 交互轨迹与工具调用：`agent/trajectory.json`、`agent/claude-code.txt`
     - 验证器判定日志：`verifier/verify.log`、`verifier/test-stdout.txt`
     - 任务定义与参考真值：`instruction.md`、`tests/refs.json` (或 `solve.sh`)
     - 全量结构化证据矩阵：`evidence.json` (含完整 timeline 时间线、contract_observations 契约对照、behavioral_signals 行为信号)
     - 决策仲裁与候选假设：`analysis.json`、`candidate-hypotheses.json`

3. `## 3. 竞争假设裁决与伴随信号` (or `## 3. Hypothesis Audit & Signals`)
   - 候选假设竞争裁决（主导假设支持证据与排除假设反驳理由）。
   - 次要伴随因素 (`contributing_factors`)。
   - 行为信号记录与文件索引（统计信号条数，指向 `evidence.json` 查看明细）。

4. `## 4. 修复行动与处方建议` (or `## 4. Recommended Actions & Notes`)
   - 针对各责任方（`Case`、`Infra`、`Verifier`、`Agent`）的整改修复建议。
   - 领域 Skill 处方建议 (`skill-prescription.md`，仅针对智能体可复用能力缺口生成)。
   - 缺失产物清单 (`missing_artifacts`，若有)。
