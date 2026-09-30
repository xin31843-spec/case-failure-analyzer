---
name: case-failure-analyzer
description: Analyze failed scientific-computing benchmark cases from job artifacts, agent trajectories, task definitions, and verifier code; attribute failures across four peer-level categories (Agent decisions, Verifier rules, Case design, or Infrastructure environment). Output concise bilingual (Chinese & English) causal audit reports with evidence file pointers.
metadata:
  short-description: Audit scientific benchmark case failures across 4 peer categories with concise reports
---

# Case Failure Analyzer

Use this skill when asked to diagnose why a scientific-computing benchmark case (`jobs/<job_name>` + `tasks/<task_name>`) failed.

It performs an end-to-end, evidence-backed causal audit across **Four Peer-Level Root Cause Categories**:
1. **智能体决策与执行失误 (`agent`)**: 细化归因智能体在科学方法选型、科学参数与截断设定、任务契约理解、工作流编排、工具调用/代码编写、结果后处理校验中的具体决策偏差。
2. **评测验证与规则判定缺陷 (`verifier`)**: 包含容差过紧碰撞、强类型比较不兼容、正则与文本解析缺陷、隐藏私有契约、重算崩溃等评测规则与判分实现缺陷。
3. **基准题目与规格设计缺陷 (`case`)**: 包含题干隐式参数未固化、题干约定缺失或语义歧义、初始资产缺失或损坏、参考真值矛盾、超时算力配额不合理。
4. **运行环境与系统设施缺陷 (`infra`)**: 包含底层容器构建/运行时崩溃、基础依赖缺失、网络连接超时、外部 API 配额耗尽等基础设施故障。

### Concise Report Standard (精简报告规范)
- **直击痛点**: 报告第 1 节直接点明直接失败原因（表象），并深入剖析更具体的内部深层根因。
- **证据解耦**: 报告第 2 节精简保留关键判分报错与首次偏离点，以清晰的 **证据链来源文件索引 (Evidence File Pointers)** 指引在 `agent/trajectory.json`、`verifier/verify.log`、`evidence.json` 等文件中查看细节，彻底杜绝平铺冗长的大型时间线与契约表格。

### Inputs

Require or discover:
- `--job`: Job directory (`jobs/<job_name>` or `jobs_failed_backup/<job_name>`) or specific trial directory (Required)
- `--output`: Output directory for evidence, analysis, and reports (Required)
- `--task`: Corresponding task definition directory (`tasks/<task_name>`) (Optional; auto-discovered or omitted when analyzing standalone job logs)

### Default Behavior & Boundaries

- **Static Post-hoc Audit**: Designed for completed jobs and trials; not an active runner daemon or real-time event watcher.
- **Strict Read-Only Input Protection**: Never modifies `tasks/`, `jobs/`, or `tests/verify.py`. `--output` cannot be identical to, inside, or a parent of `--job`, explicit `--task`, or auto-discovered task directories (including nested entries and symlinks pointing into input trials/jobs/tasks); any path overlap exits with code `2` with zero disk writes.
- **Staging Lifecycle & Transactional Publication**: Analysis is staged into an isolated temporary directory and published to `--output` transactionally using manifest-based artifact tracking (`.cfa_manifest.json`). Publishing cleans only managed artifacts across single/multi-trial switches and strictly preserves user-authored files and directories. If an error occurs during publication, an automatic rollback restores `--output` to its exact pre-publish state.
- **Deterministic Evidence Extraction + Model Causal Reasoning**: Deterministic scripts extract `evidence.json` and `candidate-hypotheses.json`; the Agent evaluates competing hypotheses per `references/attribution-protocol.md` (or validates the conservative draft in `analysis.json`).
- **Evidence-first attribution**: Never assigns a root cause from a single keyword match. Separates **failure manifestation (symptom)**, **detection stage**, and **primary root cause**.
- **Closed-Loop Three-Way Verification**: Numerical and parser defects require closed-loop corroboration between `instruction.md` (Prompt), `tests/verify.py` (Verifier rules), and runtime logs (`verify.log`). If `instruction.md` is missing, or if verifier trajectory keywords exist only in comments rather than executable Python AST assertions/comparisons, or if prompt mandates exact pointwise trajectory, numerical claims abstain conservatively to `unknown`.
- **Causal Precedence Timeline vs Gate Evaluation**: Enforces strict chronological causality: `Infra (pre-startup)` ➔ `Case (missing assets/setup defect)` ➔ `Verifier (internal crash/defect)` ➔ `Agent (positive deviation)`. The deterministic evaluation order (Gates 1 through 7) enforces this timeline and ensures isolated verifier crashes strictly attribute to `verifier` (`VERIFIER_RECOMPUTE_DEFECT`) and forbid `agent` or `unknown`.
- **Positive-evidence gate for Agent blame**: Never defaults to `agent` when other gates do not fire. Requires positive agent causal evidence (`behavioral_signals`, `agent_mismatch` contract, or unrecovered trajectory scientific errors tied to agent decisions). Ordinary trajectory events or unexplained verifier mismatches converge to `unknown`.
- **Calibrated uncertainty**: Outputs `unknown` (`UNKNOWN_INSUFFICIENT_EVIDENCE`) when evidence cannot distinguish competing hypotheses.
- **Concise Bilingual Report Output**: Always produces concise Chinese-English bilingual `report.md` (along with standalone `report.zh.md` and `report.en.md`, plus bilingual `skill-prescription.md` when eligible).

### Runtime Contract

- `scripts/analyze_case.py` is the single CLI entrypoint; `--job` and `--output` are required, `--task` is optional.
- Supported trajectory schemas: `ATIF-v1.7` (primary), plus `ATIF-v1.6` / `ATIF-v1.5`.
- Output schema version: `failure-analysis-v1` (see `references/evidence-schema.md` and `references/report-schema.md`).
- Bilingual output is mandatory for `--phase all`: `report.md`, `report.zh.md`, `report.en.md`, and `skill-prescription.md` only when eligible.
- Invalid inputs (missing `--job` or `--output`, non-existent `--job`/`--task`, unknown `--trial`, path overlap between `--output` and `--job`/`--task`, empty job tree without job-level evidence) exit with code `2` and write nothing.
- `analysis.json` carries an optional `decision_trace` recording which gate was evaluated, why each abstained, and which one was selected. It is additive and never required: a hand-authored or model-written `analysis.json` validates without one.
- `evidence.json` carries an optional `diagnostics` list recording any recovery that degraded evidence (an unparseable `tests/verify.py` or `verifier/reward.txt`). A non-empty list means some conclusion rests on less than the artifacts appear to show; the same records are printed to stderr.

### Attribution Internals

The causal decision is a fixed sequence of gates in `scripts/attribution/gates/`, run in declared order by `scripts/attribution/engine.py`. The first gate to match returns the attribution; every gate either abstains (`None`) or returns a complete 15-key result. `scripts/attribution/schema.py` enforces that contract, and `scripts/attribution/context.py` precomputes what the gates share.

Gate order is load-bearing and is pinned by tests — do not reorder gates or convert an abstaining gate into a fall-through. To change attribution behavior, edit the relevant gate; the decision-table tests in `tests/test_attribution_decisions.py` describe each gate's input conditions.

### Workflow

1. **Run Evidence Collection & Candidate Hypothesis Generation**
   Execute `scripts/analyze_case.py` (supports `--phase collect` for evidence + candidate hypotheses, or `--phase all` for end-to-end conservative attribution and bilingual report generation):
   ```bash
   python3 "${CODEX_HOME:-$HOME/.codex}/skills/case-failure-analyzer/scripts/analyze_case.py" \
     --job jobs/<job_name> \
     --task tasks/<task_name> \
     --output failure-analysis/<case_id>
   ```
2. **Gate on Per-Trial Startup & Infrastructure State (`scripts/runtime_state.py` + `scripts/extract_runtime_errors.py`)**
   Determine from `evidence.json` (`runtime.agent_started`, `runtime.verifier_started`, `runtime.execution_status`, `runtime.verification_status`, `error_observations`) whether the trial passed (`reward >= 1.0`) or whether the container/agent failed prior to startup. Job-level `stats.n_errored_trials` is never used to mark an individual passing trial as failed.
3. **Reconstruct the Unified Execution Timeline**
   Trace chronological events across runner setup, agent steps (`ATIF-v1.7`), tool calls, file writes, and verifier execution.
4. **Audit the Three-Way Contract (`Prompt <-> Verifier <-> Agent Output`)**
   Inspect `contract_observations` and `verifier_observations` (`failure_binding: direct | indirect | none`, `verifier_internal_crash`) from `scripts/audit_contract.py` to distinguish genuine agent contract violations from causally bound verifier parser defects or internal verifier crashes.
5. **Extract Scientific Software Error Events**
   Review `scientific_observations` from `scripts/extract_scientific_errors.py` (backed by the unified registry `references/error-families.json`) and consult `references/software/<software>.md` for discriminating evidence requirements.
6. **Identify the First Unrecovered Deviation (`first_unrecovered_deviation`)**
   Record `{"status": "identified", "event_ref": "...", "summary": "..."}` or `{"status": "not_identified", "event_ref": null, "summary": "..."}` when logs are incomplete.
7. **Evaluate Competing Root-Cause Hypotheses (`candidate-hypotheses.json`)**
   Compare structured hypotheses (`H1`, `H2`, ...) with `evidence_for`, `evidence_against`, `missing_evidence`, `counterfactual_test`, and heuristic evidence scores (`scripts/confidence.py`).
8. **Assign Primary Root Cause & Contributing Factors**
   Select exactly one `primary_root_cause` and zero or more `contributing_factors`.
9. **Validate & Render Bilingual Outputs**
   Validate `evidence.json`, `analysis.json`, and `report.md` via `scripts/validate_analysis.py`, then render bilingual `report.md`, `report.zh.md`, `report.en.md` (and bilingual `skill-prescription.md` only when eligible) via `scripts/render_report.py`.

### Model-in-the-Loop Attribution (optional)

`--phase all` emits a conservative, fully deterministic draft `analysis.json`. To substitute a
model-authored attribution, write or edit `analysis.json` by hand, then validate JSON, render reports, and validate the rendered output:

```bash
# Step 1: Validate structural constraints & machine-checked hard rules on analysis.json
python3 "${CODEX_HOME:-$HOME/.codex}/skills/case-failure-analyzer/scripts/validate_analysis.py" \
  --evidence failure-analysis/<case_id>/evidence.json \
  --analysis failure-analysis/<case_id>/analysis.json

# Step 2: Render bilingual report and skill prescription
python3 "${CODEX_HOME:-$HOME/.codex}/skills/case-failure-analyzer/scripts/render_report.py" \
  --evidence failure-analysis/<case_id>/evidence.json \
  --analysis failure-analysis/<case_id>/analysis.json \
  --output-report failure-analysis/<case_id>/report.md \
  --output-prescription failure-analysis/<case_id>/skill-prescription.md \
  --lang bilingual

# Step 3: Validate the rendered report structure
python3 "${CODEX_HOME:-$HOME/.codex}/skills/case-failure-analyzer/scripts/validate_analysis.py" \
  --evidence failure-analysis/<case_id>/evidence.json \
  --analysis failure-analysis/<case_id>/analysis.json \
  --report  failure-analysis/<case_id>/report.md
```

`validate_analysis.py` deterministically verifies the machine-checkable Hard Rules below; a rejected `analysis.json` must be corrected, never rendered. Higher-level scientific domain rationale and counterfactual plausibility require expert review.

### Attribution Constraints (Hard Rules)

#### Machine-Checked Constraints (enforced by `validate_analysis.py`)
1. **Pre-startup rules (`runtime.agent_started == false`):**
   - If fatal infrastructure evidence exists -> `primary_root_cause.category` MUST be `infra`.
   - If no infrastructure/exception logs exist -> `primary_root_cause.category` MUST be `unknown` (`UNKNOWN_INSUFFICIENT_EVIDENCE`).
   - `primary_root_cause.category` is **STRICTLY FORBIDDEN** from being `agent`.
2. **Positive evidence requirement for `agent`:**
   - `reward == 0` or `FAIL` in `verify.log` alone is NOT positive agent evidence.
   - At least one positive agent signal (`behavioral_signals`, `agent_mismatch`, agent timeline error, or agent-caused `scientific_observations`) must be cited in `evidence_refs`.
3. **Verifier internal crash priority & static hazard binding:**
   - A verifier internal crash (`FileNotFoundError` on verifier temp/ref paths) MUST be attributed to `verifier` (`VERIFIER_RECOMPUTE_DEFECT`), never `agent`.
   - A static verifier hazard without direct failure binding (`failure_binding != "direct"`) cannot serve as evidence for `verifier`.
4. **Skill prescription policy:**
   - `skill_prescription` is **FORBIDDEN** unless `primary_root_cause.category` is `agent`.
5. **Structural & resolution integrity:**
   - All `evidence_refs` and hypothesis evidence pointers must resolve in `evidence.json`.
   - `first_unrecovered_deviation` and `competing_hypotheses` must be populated with valid status and evidence.
   - Rendered `report.md` must contain all 4 required bilingual section headers with non-empty content.

#### Expert / Human Review Constraints
1. **Do not classify solely from an error string or bare keyword:** Ensure that solver errors or warning strings had unrecovered downstream impact rather than transient recovery.
2. **Distinguish symptom, detection point, and root cause:** Confirm that the primary root cause reflects the earliest unrecovered deviation rather than downstream detection symptoms.
3. **Counterfactual test plausibility:** Verify that proposed counterfactual interventions in `competing_hypotheses` are scientifically meaningful and testable.
4. **Skill generalizability:** Verify that an agent skill prescription targets an enduring, reusable capability gap across scientific benchmarks rather than an ad-hoc workaround for a single task.

---

## References

Before finalizing complex attributions, consult:
- [references/taxonomy.md](references/taxonomy.md)
- [references/attribution-protocol.md](references/attribution-protocol.md)
- [references/evidence-schema.md](references/evidence-schema.md)
- [references/report-schema.md](references/report-schema.md)
- [references/skill-prescription-policy.md](references/skill-prescription-policy.md)
- [references/error-families.json](references/error-families.json)
- Domain & software knowledge bases in `references/software/` (11 suites / 60 error families):
  - [cp2k.md](references/software/cp2k.md) (`CP2K` mixed Gaussian/plane-wave DFT & AIMD)
  - [quantum-espresso.md](references/software/quantum-espresso.md) (`Quantum ESPRESSO` plane-wave DFT / DFPT)
  - [vasp-abacus.md](references/software/vasp-abacus.md) (`VASP`, `ABACUS`, `GPAW`, `Siesta`, `FHI-aims` solid-state DFT)
  - [orca-gaussian-pyscf.md](references/software/orca-gaussian-pyscf.md) (`ORCA`, `Gaussian`, `PySCF`, `Psi4`, `Q-Chem`, `NWChem` molecular quantum chemistry)
  - [lammps.md](references/software/lammps.md) (`LAMMPS` classical & reactive MD)
  - [gromacs-amber-openmm.md](references/software/gromacs-amber-openmm.md) (`GROMACS`, `AMBER`, `OpenMM`, `NAMD`, `CHARMM` biomolecular MD)
  - [mlip.md](references/software/mlip.md) (`MACE`, `NequIP`, `Allegro`, `DeePMD-kit`, `CHGNet`, `SevenNet`, `M3GNet`, `MatterSim`, `Orb` ML interatomic potentials)
  - [ase.md](references/software/ase.md) (`ASE` / `pymatgen` workflows & calculators)
  - [xtb.md](references/software/xtb.md) (`xTB` / `CREST` semiempirical quantum chemistry)
  - [rdkit.md](references/software/rdkit.md) (`RDKit` cheminformatics & conformer generation)
  - [generic-scientific.md](references/software/generic-scientific.md) (`SciPy`, `NumPy`, `JAX`, `PyTorch`, `FEniCS`, `OpenFOAM`, ODE/PDE/Linalg & unit conversion)
