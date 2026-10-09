---
name: case-failure-analyzer
description: Analyze failed scientific-computing benchmark cases from job artifacts, agent trajectories, task definitions, and verifier code; attribute failures across four peer-level categories (Agent decisions, Verifier rules, Case design, or Infrastructure environment). Output concise bilingual (Chinese & English) causal audit reports with evidence file pointers.
metadata:
  short-description: Audit scientific benchmark case failures across 4 peer categories with concise reports
---

# case failure analyzer

Diagnose why scientific-computing benchmark cases (`jobs/<job_name>` + `tasks/<task_name>`) failed via evidence-backed causal attribution across four peer-level root cause categories:
1. **`agent` (Agent Decisions & Execution)**: Method selection, parameter/cutoff settings, task contract comprehension, workflow orchestration, tool calling, code syntax, or post-processing errors.
2. **`verifier` (Verifier Rules & Scoring)**: Overly strict tolerance, type incompatibility, regex/AST parsing defect, hidden private contract, or verifier recompute crash.
3. **`case` (Benchmark & Task Design)**: Missing/damaged assets, task ambiguity, contradictory reference truth, or unreasonable timeout/compute quota.
4. **`infra` (Runtime & Infrastructure)**: Container/pre-startup failure, missing system dependencies, network timeout, or hardware OOM.

### CLI & Input Contract

Entrypoint: `python3 scripts/analyze_case.py`
- Required:
  - `--job <path>`: Job directory (`jobs/<job_name>`) or specific trial directory.
  - `--output <path>`: Output directory for analysis artifacts (isolated; inputs are strictly read-only and cannot overlap with `--output`).
- Optional:
  - `--task <path>`: Task definition directory (`tasks/<task_name>`); auto-discovered if omitted.
  - `--trial <name|all>`: Target specific trial name or all trials (default: `all`).
  - `--lang {bilingual,zh,en}`: Report language edition (default: `bilingual`).
  - `--format {both,json,markdown}`: Output format (default: `both`).
  - `--phase {all,collect}`: `all` for full pipeline + attribution + reports (default); `collect` for evidence & candidate hypotheses only.
  - `--replay {none}`: Post-hoc audit mode (default: `none`).
  - `--max-log-bytes <n>`: Maximum bytes per log file read (default: `120000`).
  - `--include-session-files`: Include agent session files in inventory.

### Output Standards

- **Single-Trial Artifacts**:
  - `evidence.json`: Normalized runtime state, trajectory timeline, contract audit, and scientific error observations.
  - `candidate-hypotheses.json`: Competing causal hypotheses scored by evidence strength.
  - `analysis.json`: Structured attribution (`failure-analysis-v1`) with root cause code, failure stage, and evidence pointers.
  - `report.md` (bilingual), `report.zh.md` (Chinese), `report.en.md` (English): High-signal audit reports with evidence file pointers (lightweight 2-section view < 30 lines for passed trials).
  - `skill-prescription.md`: Bilingual domain skill prescription (generated **only** for reusable Agent capability gaps).
- **Multi-Trial Batch Board**:
  - `job_summary.md`: Markdown summary dashboard table showing verdicts, categories, root causes, and failure stages across all trials.
  - `job_summary.json`: Batch aggregated statistics and per-trial summary records.

### 3-Step Core Workflow

1. **Run Analysis**: Execute `analyze_case.py` on target job/trial to extract evidence, evaluate hypotheses, and generate reports:
   ```bash
   python3 scripts/analyze_case.py --job jobs/<job_name> --task tasks/<task_name> --output failure-analysis/<case_id>
   ```
2. **Review Reports & Evidence**: Inspect `report.md` (or `job_summary.md` for batch jobs). Review primary failure manifestations, then inspect referenced evidence files (`evidence.json`, `verify.log`, `trajectory.json`) via file pointers.
3. **Validate & Refine (Optional Model-in-the-Loop)**: When modifying hypotheses or refining attributions, edit `analysis.json` and validate machine-checkable hard rules:
   ```bash
   python3 scripts/validate_analysis.py --evidence <dir>/evidence.json --analysis <dir>/analysis.json [--report <dir>/report.md]
   python3 scripts/render_report.py --evidence <dir>/evidence.json --analysis <dir>/analysis.json --output-report <dir>/report.md --lang bilingual
   ```

### Core Attribution Hard Rules

- **Pre-startup Boundary**: When `runtime.agent_started == false`, attribution MUST be `infra` (if fatal setup error) or `unknown` (`UNKNOWN_INSUFFICIENT_EVIDENCE`). Blaming `agent` is **STRICTLY FORBIDDEN**.
- **Verifier Crash Priority**: An unhandled verifier crash/exception (`FileNotFoundError`, syntax error, recompute crash) MUST be attributed to `verifier` (`VERIFIER_RECOMPUTE_DEFECT`), never `agent`.
- **Positive Agent Evidence Requirement**: Attributing failure to `agent` requires explicit positive deviation (`behavioral_signals`, contract violation, unrecovered trajectory scientific error). `reward == 0` or verifier `FAIL` alone is insufficient.
- **Closed-Loop Corroboration**: Numerical divergence claims require closed-loop cross-corroboration between prompt requirements, verifier AST rules, and runtime error logs; uncorroborated claims abstain to `unknown`.
- **Skill Prescription Scope**: `skill_prescription` is **FORBIDDEN** unless `primary_root_cause.category` is `agent`.
- **Evidence Pointer Integrity**: All `evidence_refs` in `analysis.json` must resolve to valid observation IDs in `evidence.json`.

### References (Progressive Disclosure)

Consult when refining complex attributions or checking software-specific error signatures:
- **Protocols & Schemas**: [taxonomy.md](references/taxonomy.md) | [attribution-protocol.md](references/attribution-protocol.md) | [evidence-schema.md](references/evidence-schema.md) | [report-schema.md](references/report-schema.md) | [skill-prescription-policy.md](references/skill-prescription-policy.md) | [error-families.json](references/error-families.json)
- **Scientific Software Knowledge Bases (`references/software/` - 11 suites / 60 error families)**:
  - [cp2k.md](references/software/cp2k.md) (`CP2K` mixed Gaussian/plane-wave DFT & AIMD)
  - [quantum-espresso.md](references/software/quantum-espresso.md) (`Quantum ESPRESSO` plane-wave DFT / DFPT)
  - [vasp-abacus.md](references/software/vasp-abacus.md) (`VASP`, `ABACUS`, `GPAW`, `Siesta`, `FHI-aims` solid-state DFT)
  - [orca-gaussian-pyscf.md](references/software/orca-gaussian-pyscf.md) (`ORCA`, `Gaussian`, `PySCF`, `Psi4`, `Q-Chem`, `NWChem` molecular quantum chemistry)
  - [lammps.md](references/software/lammps.md) (`LAMMPS` classical & reactive MD)
  - [gromacs-amber-openmm.md](references/software/gromacs-amber-openmm.md) (`GROMACS`, `AMBER`, `OpenMM`, `NAMD`, `CHARMM` biomolecular MD)
  - [mlip.md](references/software/mlip.md) (`MACE`, `NequIP`, `Allegro`, `DeePMD-kit`, `CHGNet`, `SevenNet` ML interatomic potentials)
  - [ase.md](references/software/ase.md) (`ASE` / `pymatgen` workflows & calculators)
  - [xtb.md](references/software/xtb.md) (`xTB` / `CREST` semiempirical quantum chemistry)
  - [rdkit.md](references/software/rdkit.md) (`RDKit` cheminformatics & conformer generation)
  - [generic-scientific.md](references/software/generic-scientific.md) (`SciPy`, `NumPy`, `JAX`, `PyTorch`, `FEniCS`, `OpenFOAM` numerics & PDE)
