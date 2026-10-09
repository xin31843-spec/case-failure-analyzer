# Report Schema (`report.md`)

Every generated `report.md` MUST include the following **4 core sections** in exact order with start-of-line headings (`## <N>. <Title>`) and non-empty body text so human reviewers and automated validators (`scripts/validate_analysis.py`) can audit the report consistently.

Following user and reviewer experience principles, reports adhere to the **Compact Attribute Table & Clean Focal Summary (紧凑属性表与聚焦高亮)** standard:
- **层级显式化**：在诊断结论中，**首先以 Markdown 属性表明确失败归属**（顶层大类 `agent` / `case` / `infra` / `verifier` ➔ 详细二级子类 `subtype` (`CODE`)）、最终裁定、阶段跃迁与置信度。
- **直击痛点**：紧接着以高亮引用卡片直截了当呈现【具体直接失败表象 (Direct Failure Cause)】与【深层内部根因 (Internal Root Cause)】。
- **门控降噪**：隐藏正常启动下的 `agent_started=True, verifier_started=True` 底层门控标记，仅在发生启动前失败或容器异常中断时才在表下附带 Warning 门控警示。
- **路径去噪与分级收敛**：精简证据文件索引，使用统一基准目录相对路径锚点；当日志全部缺失时合并为单行概括；对缺失产物分级过滤，仅展示核心输入与计算产物，收敛内部临时/中间文件。
- **自然文本表述**：消除 Python 列表原生 `repr` 语法泄露，将支持/反驳证据转换为自然文本。

Every invocation of `scripts/render_report.py` / `scripts/analyze_case.py` generates:
- `report.md`: Compact Chinese-English bilingual report with parallel bilingual labels (4 core sections, no duplicated Part II English copy).
- `report.zh.md`: Clean standalone Chinese edition (4 core sections).
- `report.en.md`: Clean standalone English edition (4 core sections).

---

## Required Sections & Visual Structure

### 1. `## 1. 诊断结论与运行态概览` (or `## 1. Verdict & Root Cause Summary`)
以紧凑 Markdown 属性表配合高亮引用呈现：
- **诊断维度属性表**：
  - **最终裁定 (Verdict)**：`failed` / `passed` / `errored`（包含执行状态、验证状态、得分）
  - **根因归属 (Root Cause)**：【大类】➔ 【二级子类】(`CODE`)
  - **阶段跃迁 (Stage Transition)**：发生阶段 ➔ 检出阶段（时间跨度）
  - **证据置信度 (Confidence)**：置信度数值与强度
- **运行门控警示 (Gate Warning)**：仅在未正常启动或容器异常中断时附带警示块，正常启动时不展示冗余门控状态。
- **高亮原因卡片**：
  - **直接失败表象 (Direct Cause)**：表面判分失败与异常现象。
  - **深层内部根因 (Internal Root Cause)**：深层模型盲区、契约歧义或判分缺陷机理。

### 2. `## 2. 故障现场与因果证据链` (or `## 2. Failure Manifestation & Evidence Chain`)
- **关键失败报错摘要**：提炼最核心的 1~3 行验证器错误日志。
- **首次不可恢复偏离点 (`first_unrecovered_deviation`)**：记录偏离事件 ref、时间戳与发生动作。
- **核心证据引用代号 (`evidence_refs`)**。
- **证据链来源文件索引 (Evidence File Pointers)**：
  - **相对上下文锚点**：统一标明 `case`、`trial` 与 `task` 相对标识，消除长绝对路径折行与泄露噪音。
  - **核心日志与产物**：交互轨迹（`agent/trajectory.json`）、评测日志（`verifier/verify.log`）、任务规范（`instruction.md`）、计算产物（`results.json`）。全缺时单行合并概括。
  - **全量证据矩阵索引**：指引至 `evidence.json` 与 `analysis.json`。

### 3. `## 3. 竞争假设裁决与伴随信号` (or `## 3. Hypothesis Audit & Signals`)
- **竞争假设仲裁**：美化为自然文本的候选假设支持证据与排除假设反驳理由，杜绝 Python 列表语法泄露。
- **伴随因素与异常信号**：次要伴随影响与行为信号条数统计（详细条目索引至 `evidence.json`）。

### 4. `## 4. 修复行动与处方建议` (or `## 4. Recommended Actions & Notes`)
- **针对性整改行动 (Action Items)**：按责任主体（Case/Infra/Verifier/Agent）给出明确对策。
- **领域 Skill 处方**：针对智能体能力盲区推荐的领域协议技能。
- **核心缺失产物清单**：仅展示关键核心输入与计算产物，收敛内部临时/中间文件。

---

## Lightweight View for Passed Trials (通过案例精简版)

当评测判定为通过 (`verdict == "passed"`) 时，报告自动切换为轻量精简视图（严格预算控制在 30 行以内），仅保留通过裁定与验证证据，彻底移除失败根因、竞争失败假设、缺失产物清单与修复行动等无关噪音：

### 1. `## 1. 评测裁定与通过概览` (or `## 1. Verdict & Pass Summary`)
- **通过裁定属性表**：最终裁定 (`passed`)、执行阶段 (`passed`)、置信度 (`1.00`)。
- **通过依据**：明确标注评测规则全部通过，未检测到未恢复异常或规格违规。

### 2. `## 2. 验证证据与产物索引` (or `## 2. Verification Evidence & Artifacts`)
- **用例与试次标识**：`case`, `trial`, `task` 相对标识，不输出任何机器绝对路径。
- **已验证产物记录**：仅展示实际存在的验证产物文件，不列出失败产物缺失项。
- **全量验证矩阵索引**：指引至 `evidence.json` 与 `analysis.json`（若使用 `--format markdown` 则展示对应说明）。

