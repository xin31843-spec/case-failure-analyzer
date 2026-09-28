---
name: case-failure-analyzer
description: Analyze failed scientific-computing benchmark cases from job artifacts, agent trajectories, task definitions, and verifier code; attribute failures to case specification, infrastructure, agent behavior, scientific decisions, verifier defects, or numerical nondeterminism. Output bilingual (Chinese & English) causal audit reports.
metadata:
  short-description: Audit scientific benchmark case failures and root causes
---

# Case Failure Analyzer

Use this skill when asked to diagnose why a scientific-computing benchmark case (`jobs/<job_name>` + `tasks/<task_name>`) failed.

It performs an end-to-end, evidence-backed causal audit rather than naive log keyword matching:
**Artifact Collection → Unified Runtime State → Timeline Reconstruction → Contract Audit → Scientific Error Diagnosis → Candidate Hypothesis Competition → Causal Attribution → Bilingual Report & Skill Prescription**

### Inputs

Require or discover:
- `--job`: Job directory (`jobs/<job_name>` or `jobs_failed_backup/<job_name>`) or specific trial directory
- `--task`: Corresponding task definition directory (`tasks/<task_name>`)

### Default Behavior & Boundaries

- **Read-only by default**: Never modifies `tasks/`, `jobs/`, or `tests/verify.py`.
- **Deterministic Evidence Extraction + Model Causal Reasoning**: Deterministic scripts extract `evidence.json` and `candidate-hypotheses.json`; the Agent evaluates competing hypotheses per `references/attribution-protocol.md` (or validates the conservative draft in `analysis.json`).
- **Evidence-first attribution**: Never assigns a root cause from a single keyword match. Separates **failure manifestation (symptom)**, **detection stage**, and **primary root cause**.
- **Positive-evidence gate for Agent blame**: Never defaults to `agent` when other gates do not fire. Requires positive agent evidence (`behavioral_signals`, `agent_mismatch` contract, or agent-caused `scientific_observations`).
- **Calibrated uncertainty**: Outputs `unknown` (`UNKNOWN_INSUFFICIENT_EVIDENCE`) when evidence cannot distinguish competing hypotheses.
- **Bilingual Report Output**: Always produces a Chinese-English bilingual `report.md` (along with standalone `report.zh.md` and `report.en.md`, plus bilingual `skill-prescription.md` when eligible).

### Runtime Contract

- `scripts/analyze_case.py` is the single entrypoint; it is **read-only** unless `--output` is supplied.
- Supported trajectory schemas: `ATIF-v1.7` (primary), plus `ATIF-v1.6` / `ATIF-v1.5`.
- Output schema version: `failure-analysis-v1` (see `references/evidence-schema.md` and `references/report-schema.md`).
- Bilingual output is mandatory for `--phase all`: `report.md`, `report.zh.md`, `report.en.md`, and `skill-prescription.md` only when eligible.
- Invalid inputs (missing `--job`/`--task`, unknown `--trial`, empty job tree without job-level evidence) exit with code `2` and write nothing.

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
model-authored attribution, write or edit `analysis.json` by hand and validate/render it explicitly:

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

`validate_analysis.py` enforces every Hard Rule below; a rejected `analysis.json` must be corrected, never rendered.

### Attribution Constraints (Hard Rules)

1. **Do not classify solely from an error string or bare keyword.** A `Connection failed`, `SCF NOT CONVERGED`, or bare `chaotic` string is only causal if supported by structured evidence and unrecovered downstream impact.
2. **Distinguish symptom, detection point, and root cause.** A failure detected in `verifier_execution` (`FAIL: ...`) may be caused by `verifier` (parser defect or internal crash), `case` (ambiguous spec or missing asset), `agent` (wrong calculation), or `numerical` drift.
3. **Pre-startup rule (`runtime.agent_started == false`):**
   - If `runtime.agent_started == false` AND fatal infrastructure evidence exists -> `primary_root_cause.category` MUST be `infra`.
   - If `runtime.agent_started == false` AND no infrastructure/exception logs exist -> `primary_root_cause.category` MUST be `unknown` (`UNKNOWN_INSUFFICIENT_EVIDENCE`).
   - If `runtime.agent_started == false` -> `primary_root_cause.category` is **STRICTLY FORBIDDEN** from being `agent`.
4. **Positive evidence is required for `agent` attribution.** `reward == 0` or `FAIL` in `verify.log` alone is NOT positive agent evidence. At least one positive agent signal (`behavioral_signals`, `agent_mismatch`, agent timeline error, or agent-caused `scientific_observations`) must be cited.
5. **A static verifier hazard must be causally bound (`failure_binding == "direct"`).** An unrelated `1.23D+03` reference number in `verify.log` when the agent wrote `9.99E+02` must NOT trigger `verifier`. Conversely, a verifier internal crash (`FileNotFoundError` on verifier temp/ref paths) MUST be attributed to `verifier` (`VERIFIER_RECOMPUTE_DEFECT`), never `agent`.
6. **Use `unknown` when evidence cannot distinguish competing hypotheses.**
7. **Generate `skill-prescription.md` ONLY for reusable, generalizable agent capability gaps.** Never generate a domain skill to work around an infrastructure failure, case defect, or verifier bug.

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
