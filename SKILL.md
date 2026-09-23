---
name: Case-Failure-Analyzer
description: Analyze failed scientific-computing benchmark cases from job artifacts, agent trajectories, task definitions, and verifier code; attribute failures to case specification, infrastructure, agent behavior, scientific decisions, verifier defects, or numerical nondeterminism.
---

# Case-Failure-Analyzer (Scientific Case Failure Analyzer)

Use this skill when asked to diagnose why a scientific-computing benchmark case (`jobs/<job_name>` + `tasks/<task_name>`) failed.

It performs an end-to-end, evidence-backed causal audit rather than naive log keyword matching:
**Artifact Collection → Timeline Reconstruction → Contract Audit → Scientific Error Diagnosis → Causal Attribution → Remediation & Skill Prescription**

## Inputs

Require or discover:
- `--job`: Job directory (`jobs/<job_name>` or `jobs_failed_backup/<job_name>`) or specific trial directory
- `--task`: Corresponding task definition directory (`tasks/<task_name>`)

## Default Behavior & Boundaries

- **Read-only by default**: Never modifies `tasks/`, `jobs/`, or `tests/verify.py`.
- **No expensive recomputation by default**: Does not run expensive DFT/MD simulations unless `--replay safe` is explicitly requested.
- **Evidence-first attribution**: Never assigns a root cause from a single keyword match. Separates **failure manifestation (symptom)**, **detection stage**, and **primary root cause**.
- **Calibrated uncertainty**: Outputs `unknown` (`UNKNOWN_INSUFFICIENT_EVIDENCE`) when evidence cannot distinguish competing hypotheses.

## Workflow

1. **Run Artifact Discovery & Normalization**
   Execute `scripts/analyze_case.py` (or the individual pipeline scripts in `scripts/`):
   ```bash
   python3 Case-Failure-Analyzer/scripts/analyze_case.py \
     --job jobs/<job_name> \
     --task tasks/<task_name> \
     --output failure-analysis/<case_id>
   ```
2. **Gate on Startup & Infrastructure State**
   Determine from `evidence.json` (`runtime.agent_started`, `runtime.verifier_started`, `error_observations`) whether the container built and the agent actually started.
3. **Reconstruct the Unified Execution Timeline**
   Trace chronological events across runner setup, agent steps (`ATIF-v1.7`), tool calls, file writes, and verifier execution.
4. **Audit the Three-Way Contract (`Prompt <-> Verifier <-> Agent Output`)**
   Inspect `contract_observations` from `scripts/audit_contract.py` to detect undocumented verifier requirements, parser/regex bugs (e.g., namelist `/` truncation, implicit `thermo_style` column indices, Fortran `D+03` exponents), or genuine agent contract violations.
5. **Extract Scientific Software Error Events**
   Review `scientific_observations` from `scripts/extract_scientific_errors.py` and consult `references/software/<software>.md` for discriminating evidence requirements.
6. **Identify the First Unrecovered Deviation (`first_unrecovered_deviation`)**
   Trace backward from the final failure manifestation to the earliest unrecovered error or decision point.
7. **Evaluate Competing Root-Cause Hypotheses**
   Generate structured hypotheses (`H1`, `H2`, ...) with `evidence_for`, `evidence_against`, `missing_evidence`, and `counterfactual_test`.
8. **Assign Primary Root Cause & Contributing Factors**
   Select exactly one `primary_root_cause` and zero or more `contributing_factors`.
9. **Validate & Render Outputs**
   Validate `evidence.json` and `analysis.json` via `scripts/validate_analysis.py`, then render `report.md` (and `skill-prescription.md` only when eligible).

## Attribution Constraints (Hard Rules)

1. **Do not classify solely from an error string.** A `Connection failed` or `SCF NOT CONVERGED` line is only causal if it was unrecovered and directly produced the final failure.
2. **Distinguish symptom, detection point, and root cause.** A failure detected in `verifier_execution` (`FAIL: ...`) may be caused by `verifier` (parser defect), `case` (ambiguous spec), `agent` (wrong calculation), or `numerical` drift.
3. **Missing trajectory before agent startup is NOT an agent failure.** If `runtime.agent_started == false` (e.g., Docker `apt` / layer pull error), `primary_root_cause.category` MUST be `infra`.
4. **A verifier failure is not automatically a verifier defect, nor automatically an agent error.** Compare `instruction.md` requirements against `tests/verify.py` AST and the agent's generated files.
5. **A scientific software error is not automatically an agent scientific error.** Check whether the provided input asset or pseudopotential was defective (`case`) or resource-killed (`infra`).
6. **Use `unknown` when evidence cannot distinguish competing hypotheses.**
7. **Generate `skill-prescription.md` ONLY for reusable, generalizable agent capability gaps.** Never generate a domain skill to work around an infrastructure failure or a verifier bug.

## References

Before finalizing complex attributions, consult:
- [references/taxonomy.md](references/taxonomy.md)
- [references/attribution-protocol.md](references/attribution-protocol.md)
- [references/evidence-schema.md](references/evidence-schema.md)
- [references/report-schema.md](references/report-schema.md)
- [references/skill-prescription-policy.md](references/skill-prescription-policy.md)
- Software knowledge bases in `references/software/`:
  - [cp2k.md](references/software/cp2k.md)
  - [quantum-espresso.md](references/software/quantum-espresso.md)
  - [lammps.md](references/software/lammps.md)
  - [ase.md](references/software/ase.md)
  - [xtb.md](references/software/xtb.md)
  - [rdkit.md](references/software/rdkit.md)
