# case-failure-analyzer (中英双版 / Bilingual Scientific Case Failure Analyzer)

An evidence-first causal failure analysis skill and toolkit for scientific-computing benchmark cases (`CP2K`, `Quantum ESPRESSO`, `LAMMPS`, `xTB`, `ASE`, `RDKit`).
面向科学计算基准评测（`CP2K`、`Quantum ESPRESSO`、`LAMMPS`、`xTB`、`ASE`、`RDKit`）的证据优先因果失败审计 Skill 与工具集。

---

## Architecture / 架构流程

```text
Artifact Collectors (discover_artifacts.py + runtime_state.py + extract_runtime_errors.py)
       ↓
Objective Evidence (evidence.json)
       ↓
Candidate Hypotheses (generate_hypotheses.py -> candidate-hypotheses.json)
       ↓
Causal Attribution Engine / Agent Protocol (analyze_case.py + attribution-protocol.md -> analysis.json)
       ↓
Schema & Invariant Validator (validate_analysis.py)
       ↓
Bilingual Reports (render_report.py -> report.md, report.zh.md, report.en.md, skill-prescription.md)
```

---

## Usage / 使用方法

All commands use the skill-relative entrypoint. Running from inside the skill folder, the equivalent short form is `python3 scripts/analyze_case.py ...`.

### 1. Full End-to-End Analysis & Bilingual Report Generation / 全流程归因与中英双版报告生成

```bash
python3 "${CODEX_HOME:-$HOME/.codex}/skills/case-failure-analyzer/scripts/analyze_case.py" \
  --job jobs/<job_name> \
  --task tasks/<task_name> \
  --output failure-analysis/<case_id>
```

Outputs generated in `failure-analysis/<case_id>/` / 输出文件：
- `evidence.json`: Objective per-trial artifacts, unified `runtime_state`, normalized trajectory timeline, contract audit matrix, and scientific error observations.
- `candidate-hypotheses.json`: Competing root-cause hypotheses with heuristic evidence strength scores.
- `analysis.json`: Causal attribution (`failure-analysis-v1`) — a conservative deterministic draft under `--phase all`.
- `report.md`: **Chinese-English Bilingual Report (中英双语对照版 + 英文全集版)** covering all 11 mandatory review sections.
- `report.zh.md`: Standalone Chinese report (纯中文版).
- `report.en.md`: Standalone English report (纯英文版).
- `skill-prescription.md`: Bilingual domain skill prescription (generated **only** for reusable Agent capability gaps).

### 2. Evidence & Candidate Hypothesis Collection Only (`--phase collect`) / 仅执行证据采集与候选假设生成

```bash
python3 "${CODEX_HOME:-$HOME/.codex}/skills/case-failure-analyzer/scripts/analyze_case.py" \
  --job jobs/<job_name> \
  --task tasks/<task_name> \
  --output failure-analysis/<case_id> \
  --phase collect
```

### 3. Model-in-the-Loop Validation & Rendering / 模型裁决结果的校验与渲染

`--phase all` emits a conservative deterministic draft. To submit a model-authored attribution, validate then render it:

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

## Exit Codes / 退出码

| Code | Meaning |
|---|---|
| `0` | Analysis succeeded (including a legitimate job-level pre-startup failure). |
| `2` | Invalid input: missing `--job`/`--task` path, unknown `--trial`, empty job tree without job-level evidence, or an unimplemented `--replay` mode. |

The entrypoint fails fast **before** writing any report, so a wrong path can never yield a plausible-looking analysis.

---

## Running Tests / 运行测试

```bash
pytest tests/
# or
python3 -m unittest discover -s tests
```
