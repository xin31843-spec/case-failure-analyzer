# Report Schema (`report.md`)

**[English](report-schema.md) | [简体中文](../zh/report-schema.md)**

Every generated `report.md` MUST include the following **4 core sections** in exact order with start-of-line headings (`## <N>. <Title>`) and non-empty body text so human reviewers and automated validators (`scripts/validate_analysis.py`) can audit the report consistently.

Following user and reviewer experience principles, reports adhere to the **Clean Bolded Key-Value List (清晰加粗键值列表与精简索引)** standard:
- **层级显式化**：在诊断结论中，**首先明确失败原因归属的顶层大类**（`agent` / `case` / `infra` / `verifier`），紧接着**附上所属的详细二级子类**（如 `scientific_method_selection` / `tolerance_too_strict`）。
- **直击痛点**：直接点明具体直接失败表象（如验证器报出何种不符、缺少何种文件），并深入剖析更具体的内部深层物理与工程机理。
- **证据解耦**：彻底摒弃平铺冗长的大型时间线表格和全量契约对照表，以结构化 **证据链来源文件索引 (Evidence File Pointers)** 指引评审人在 `agent/trajectory.json`、`verifier/verify.log`、`evidence.json` 等具体文件中按需查看原始数据。

Every invocation of `scripts/render_report.py` / `scripts/analyze_case.py` generates:
- `report.md`: Unified Chinese-English bilingual report containing Part I (Chinese-English side-by-side with the 4 canonical headers) and Part II (Complete English Edition).
- `report.zh.md`: Standalone Chinese edition (4 core sections).
- `report.en.md`: Standalone English edition (4 core sections).

---

## Required Sections & Visual Structure

### 1. `## 1. 诊断结论与运行态概览` (or `## 1. Verdict & Root Cause Summary`)
以视觉清晰的加粗列表呈现：
- **根因分类归属**：`【大类】...` ➔ `【二级子类】... (CODE)`  
- **裁定与运行门控**：`failed` / `passed` / `errored` (得分、执行状态、验证状态、启动门禁)  
- **阶段跃迁轨迹**：发生阶段 ➔ 检出阶段（置信度与证据强度）  
- **具体失败原因 (Direct Cause)**：直接点明表面判分失败表象。  
- **深层内部根因 (Internal Root Cause)**：剖析深层模型盲区、契约歧义或判分缺陷机理。  
- **证据置信度 (Confidence)**：置信度数值与强度。

### 2. `## 2. 故障现场与因果证据链` (or `## 2. Failure Manifestation & Evidence Chain`)
- **关键失败报错摘要**：提炼最核心的 1~3 行验证器错误日志。
- **首次不可恢复偏离点 (`first_unrecovered_deviation`)**：记录偏离事件 ref、时间戳与发生动作。
- **核心证据引用代号 (`evidence_refs`)**。
- **证据链来源文件索引 (Evidence File Pointers)**：
  - 智能体交互轨迹与命令：`agent/trajectory.json`、`agent/claude-code.txt`
  - 验证器判定与执行日志：`verifier/verify.log`、`verifier/test-stdout.txt`
  - 任务规范与参考真值：`instruction.md`、`tests/refs.json` (或 `solve.sh`)
  - 全量因果证据矩阵：`evidence.json` (完整 timeline、契约比对、行为信号)
  - 结构化归因与决策记录：`analysis.json`、`candidate-hypotheses.json`

### 3. `## 3. 竞争假设裁决与伴随信号` (or `## 3. Hypothesis Audit & Signals`)
- **竞争假设仲裁**：候选假设支持证据与排除假设反驳理由。
- **伴随因素与异常信号**：次要伴随影响与行为信号条数统计（索引至 `evidence.json`）。

### 4. `## 4. 修复行动与处方建议` (or `## 4. Recommended Actions & Notes`)
- **针对性整改行动 (Action Items)**：按责任主体（Case/Infra/Verifier/Agent）给出明确对策。
- **领域 Skill 处方**：针对智能体能力盲区推荐的领域协议技能。
- **缺失产物清单**（若有）。
