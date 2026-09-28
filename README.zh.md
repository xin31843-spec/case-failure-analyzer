# Case Failure Analyzer（科学计算基准用例失败因果分析器）

**[English](README.md) | [简体中文](README.zh.md)**

面向科学计算与机器学习势（MLIP）基准评测（`CP2K`、`Quantum ESPRESSO`、`VASP/ABACUS`、`ORCA/Gaussian/PySCF`、`LAMMPS`、`GROMACS/AMBER/OpenMM`、`MLIP (MACE/NequIP/DeePMD/CHGNet)`、`ASE`、`xTB`、`RDKit`、`SciPy/NumPy/JAX/PyTorch/FEniCS/OpenFOAM`）的证据优先（Evidence-First）因果失败审计 Skill 与工具集。

---

## 说明文档索引

| 文档名称 | 中文版 (`docs/zh/`) | 英文版 (`docs/en/`) |
|---|---|---|
| **项目概览与命令行使用指南** | [README.zh.md](README.zh.md) | [README.md](README.md) |
| **系统工作流与归因总规范** | [docs/zh/guide.md](docs/zh/guide.md) | [docs/en/guide.md](docs/en/guide.md) |
| **失败分类学规范 (`failure-analysis-v1`)** | [docs/zh/taxonomy.md](docs/zh/taxonomy.md) | [docs/en/taxonomy.md](docs/en/taxonomy.md) |
| **逆向因果归因协议** | [docs/zh/attribution-protocol.md](docs/zh/attribution-protocol.md) | [docs/en/attribution-protocol.md](docs/en/attribution-protocol.md) |
| **证据与归因 JSON 模式规范** | [docs/zh/evidence-schema.md](docs/zh/evidence-schema.md) | [docs/en/evidence-schema.md](docs/en/evidence-schema.md) |
| **审计报告结构规范（4 大核心板块）** | [docs/zh/report-schema.md](docs/zh/report-schema.md) | [docs/en/report-schema.md](docs/en/report-schema.md) |
| **领域技能处方生成策略** | [docs/zh/skill-prescription-policy.md](docs/zh/skill-prescription-policy.md) | [docs/en/skill-prescription-policy.md](docs/en/skill-prescription-policy.md) |

> **关于 Agent 专用文件的说明**：根目录下的 `SKILL.md` 及 `references/` 目录（含 `references/*.md`、`references/software/*.md` 与 `references/error-families.json`）专供 Agent 运行时读取，统一保留纯英文版本以节约上下文开销。人类开发者阅读请查阅上表中的 `docs/zh/` 与 `docs/en/` 双版本目录。

---

## 架构流程

```text
产物与状态采集 (discover_artifacts.py + runtime_state.py + extract_runtime_errors.py)
       ↓
客观证据数据 (evidence.json)
       ↓
竞争假设生成 (generate_hypotheses.py -> candidate-hypotheses.json)
       ↓
因果归因引擎 / Agent 裁决协议 (analyze_case.py + attribution-protocol.md -> analysis.json)
       ↓
Schema 与硬规则校验器 (validate_analysis.py)
       ↓
中英双语审计报告渲染 (render_report.py -> report.md, report.zh.md, report.en.md, skill-prescription.md)
```

---

## 使用方法

所有命令均通过入口脚本执行。若在 Skill 根目录内运行，可直接使用简写形式 `python3 scripts/analyze_case.py ...`。

### 1. 全流程归因与中英双版报告生成

```bash
python3 "${CODEX_HOME:-$HOME/.codex}/skills/case-failure-analyzer/scripts/analyze_case.py" \
  --job jobs/<job_name> \
  --task tasks/<task_name> \
  --output failure-analysis/<case_id>
```

在 `failure-analysis/<case_id>/` 目录下生成的输出文件：
- `evidence.json`：单 Trial 客观产物清单、统一运行态 `runtime_state`、标准化轨迹时间线、三方契约审计矩阵及科学软件错误观测。
- `candidate-hypotheses.json`：带启发式证据强度评分的竞争根因假设列表。
- `analysis.json`：因果归因结构化结果（`failure-analysis-v1`）——在 `--phase all` 下默认生成保守的确定性草稿。
- `report.md`：**中英双语合订审计报告**（包含 4 个高信噪比核心板块与按需展开的动态子块）。
- `report.zh.md`：独立纯中文审计报告。
- `report.en.md`：独立纯英文审计报告。
- `skill-prescription.md`（及 `skill-prescription.zh.md`、`skill-prescription.en.md`）：中英双语领域技能处方（**仅**在判定为可复用的 Agent 能力缺口时生成）。

### 2. 仅执行证据采集与候选假设生成 (`--phase collect`)

```bash
python3 "${CODEX_HOME:-$HOME/.codex}/skills/case-failure-analyzer/scripts/analyze_case.py" \
  --job jobs/<job_name> \
  --task tasks/<task_name> \
  --output failure-analysis/<case_id> \
  --phase collect
```

### 3. 模型介入裁决结果的校验与渲染

`--phase all` 默认产出保守的确定性归因草稿。如需提交由模型编写或修订的归因结论，请先执行校验再渲染报告：

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

---

## 退出码说明

| 退出码 | 含义 |
|---|---|
| `0` | 分析成功完成（包括合法的 Job 级启动前基础设施失败）。 |
| `2` | 无效输入：`--job` 或 `--task` 路径不存在、指定的 `--trial` 不存在、空作业目录且无 Job 级证据，或请求了未实现的 `--replay` 模式。 |

入口脚本会在写出任何报告文件**之前**执行快速失败校验，避免错误路径产出看似合理的误导性报告。

---

## 运行测试

```bash
pytest tests/
# 或
python3 -m unittest discover -s tests
```
