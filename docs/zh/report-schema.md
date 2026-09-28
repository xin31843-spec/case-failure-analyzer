# 审计报告结构规范 (`report.md`)

**[English](../en/report-schema.md) | [简体中文](report-schema.md)**

每份生成的 `report.md` 必须按严格顺序包含以下 **4 个高信噪比核心板块**（且每个章节标题必须位于行首 `## <N>. <Title>` 并具有非空正文），既消除原 11 章节中的重复打印与空白占位符噪音，又保留完整的因果证据链以便人工审阅与自动校验器（`scripts/validate_analysis.py`）核验。

每次调用 `scripts/render_report.py` / `scripts/analyze_case.py` 均会生成：
- `report.md`：统一**中英双语合订版报告**（包含第 I 部分中英对照的 4 个标准核心板块，以及第 II 部分完整英文版）。
- `report.zh.md`：独立纯中文版报告（4 个标准板块）。
- `report.en.md`：独立纯英文版报告（4 个标准板块）。

---

## 必备的 4 个核心板块 (`Required Sections`)

1. `## 1. 诊断结论与运行态概览`（或 `## 1. Verdict & Root Cause Summary`）
   - **合并原第 1、2、5 节，消除重复打印**：一屏展示最终裁定与运行门控快照（`verdict`、`execution_status`、`verification_status`、`reward`、`agent_started`、`verifier_started`）、**唯一主根因**（`category` / `subtype` / `code` / `confidence` / `evidence_strength`）、**发生阶段 → 检出阶段**转换，以及唯一一份完整的因果传导机制说明（`primary_root_cause.summary`）。
2. `## 2. 故障现场与因果证据链`（或 `## 2. Failure Manifestation & Evidence Chain`）
   - **合并原第 3、4、7 节，串联完整证据链并支持动态折叠**：
     - 直接失败表象（`failure_manifestation.type`、`summary` 及原始验证器报错片段摘录）；
     - 首次不可恢复偏离点（`first_unrecovered_deviation`）及核心证据引用（`evidence_refs`）；
     - **按需展开**：仅当存在轨迹事件时渲染执行时间线表格；仅当触发契约核查项时渲染三方契约矩阵（`Prompt ↔ Verifier ↔ Agent Output`），不再打印无意义的空白章节。
3. `## 3. 竞争假设裁决与伴随信号`（或 `## 3. Hypothesis Audit & Signals`）
   - **合并原第 6、8 节，聚焦因果辩证**：
     - 结构化展示竞争性候选假设（`competing_hypotheses`）得分与支持/反驳证据，以及排除其他假设的理由（`excluded_hypotheses`）；
     - **按需展开**：仅当存在次要伴随因素（`contributing_factors`）或异常行为信号（`behavioral_signals`）时动态挂载展示。
4. `## 4. 修复行动与处方建议`（或 `## 4. Recommended Actions & Notes`）
   - **合并原第 9、10、11 节，聚焦可执行动作**：
     - 按责任方（`Case`、`Infra`、`Verifier`、`Agent Policy`）给出具体修复建议（`recommended_actions`）；
     - **按需展开**：仅当满足 5 项准入门槛并生成 `skill-prescription.md` 时展示领域 Skill 处方摘要；仅当存在缺失产物（`missing_artifacts`）时提示取证边界。
