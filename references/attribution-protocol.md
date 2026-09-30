# Causal Attribution Protocol

Every failure analysis MUST follow this 7-step backward causal trace protocol. Do not jump from an error log line directly to a root cause label.

---

## 1. Backward Causal Trace Order

For every failed trial:

1. **Identify the Final Failure Manifestation**
   - What caused the trial to be marked failed (`reward < 1.0` or `exception_info != null`)? Note: If `reward >= 1.0` (`verification_status == "passed"`), the trial passed and must NEVER be polluted by job-level `stats.n_errored_trials`.
2. **Trace Backward to the Immediate Artifact State**
   - Inspect how the missing/invalid file or value was produced and compare the three-way contract: `instruction.md` (Prompt) vs `tests/verify.py` (Verifier) vs Agent's outputs.
3. **Locate the First Error Decision or Abnormal State**
   - Walk backward through normalized trajectory events (`trajectory:step:N`) to find where the state first diverged from a valid solution path.
4. **Assess Recoverability**
   - Distinguish recoverable container-side issues from unrecoverable defects (e.g., container build failure, missing task asset, or causally bound verifier parser/internal crash).
5. **Check Agent Observation**
   - Did the agent observe the error message or anomalous value in a tool output?
6. **Check Agent Recovery Actions**
   - Did the agent diagnose the error and adjust parameters appropriately, or did it repeat the failed action (`repeated_failed_action`) / ignore the error?
7. **Pinpoint the First Unrecovered Deviation (`first_unrecovered_deviation`)**
   - Record `{"status": "identified", "event_ref": "<valid_id>", "summary": "..."}` or `{"status": "not_identified", "event_ref": null, "summary": "..."}` when logs are incomplete.

---

## 2. Causal Precedence Timeline & Gate Evaluation Order

All causal attribution enforces a strict chronological dependency timeline:
$$\text{Infra (pre-startup)} \longrightarrow \text{Case (assets/setup)} \longrightarrow \text{Verifier (crash/parser/tolerance)} \longrightarrow \text{Agent (positive deviation)}$$

To implement this timeline deterministically, the engine evaluates gates in declared order:
1. **Gate 1: Pre-Startup Infrastructure (`gate1_infra`)**: Fatal infra error when `agent_started == false` attributes to `infra`. Silent pre-startup failure without logs attributes to `unknown`.
2. **Gate 2: Case Assets & Setup Defect (`gate2_case`)**: Missing prompt assets or broken container setup attributes to `case`.
3. **Gate 3: Verifier Defect (`gate3_verifier`)**: Internal verifier crashes (`VERIFIER_RECOMPUTE_DEFECT`) or causally bound parser hazards (`failure_binding == "direct"`) attribute to `verifier`.
4. **Gate 4: Numerical / Tolerance Defect (`gate4_numerical`)**: Structured numerical divergence with matching ensemble statistics and proven closed loop attributes to `verifier` (`VERIFIER_TOLERANCE_TOO_STRICT`).
5. **Gate 5: Insufficient Evidence Check (`gate5_insufficient`)**: If required positive agent evidence is missing, abstains to `unknown` and prevents false agent blame.
6. **Gate 6: Agent Primary Decision Error (`gate6_agent_primary`)**: Validates all 5 necessary gate conditions and positive behavioral signals before attributing to `agent`.
7. **Gate 7: Unknown Fallback (`gate7_unknown`)**: Safe conservative fallback.

| Precedence Stage | Gate | Scope / Trigger | Required Category | Forbidden Defaults |
| :--- | :--- | :--- | :--- | :--- |
| **Stage 1: Pre-Startup Infra** | Gate 1 | `agent_started == false` with fatal infra error | `infra` | Never `agent` |
| **Stage 1b: Pre-Startup Silent**| Gate 1 | `agent_started == false` with no infra evidence | `unknown` | Never `agent` |
| **Stage 2: Case Assets/Setup** | Gate 2 | Missing prompt assets or broken container setup | `case` | Never `agent` |
| **Stage 3: Verifier Crash / Defect**| Gate 3 | Internal verifier crash or direct-bound parser defect | `verifier` | Never `agent` or `unknown` (isolated crash) |
| **Stage 4: Numerical Tolerance** | Gate 4 | Instantaneous trajectory drift with matching ensemble | `verifier` (if verified) | Never `agent` (abstain to `unknown` if unproven)|
| **Stage 5: Agent Decision** | Gate 6 | Positive agent behavioral/trajectory error | `agent` | Never assign without positive evidence |

### Necessary Gate Conditions for Blaming the Agent

You may assign `primary_root_cause.category = "agent"` **ONLY IF ALL FIVE** of the following conditions hold (plus at least one positive agent evidence reference):

1. **Task Completeness**: `instruction.md` provided sufficient specification, and required assets exist in the container.
2. **Infrastructure Integrity**: `runtime.agent_started == true`, and no fatal container/network/API/timeout failure blocked normal execution.
3. **Verifier Contract Alignment**: The failing verifier check corresponds to an explicit requirement in `instruction.md` and is neither a causally bound verifier parser defect (`failure_binding == "direct"`) nor a verifier internal crash (`verifier_internal_crash`).
4. **Positive Agent Evidence**: At least one positive agent signal is cited in `evidence_refs` (`behavioral_signals`, `agent_mismatch` contract, agent trajectory decision event, or agent-caused `scientific_observations`). Bare `reward=0` or `FAIL` in `verify.log` is NOT sufficient.
5. **Causal Link**: Fixing the agent's identified decision/action would directly prevent the final failure manifestation.

> **Hard Rule on Pre-Startup Failures (`runtime.agent_started == false`)**:
> - If `runtime.agent_started == false` AND fatal infrastructure evidence exists (`causal_candidate == true`) -> `primary_root_cause.category` MUST be `infra` (or `case` if the `Dockerfile` itself is broken).
> - If `runtime.agent_started == false` AND no infrastructure or exception logs exist -> `primary_root_cause.category` MUST be `unknown` (`UNKNOWN_INSUFFICIENT_EVIDENCE`).
> - Whenever `runtime.agent_started == false`, attributing `primary_root_cause.category = "agent"` (`false-agent-blame`) is **strictly forbidden**.

---

## 3. Distinguishing Verifier Defects vs Agent Errors

When `verifier/verify.log` outputs an error or `FAIL: <msg>`:

- **Check 1 — Verifier Internal Crash (`VERIFIER_RECOMPUTE_DEFECT`)**:
  If `verify.py` crashes on its own internal paths/files (e.g., `FileNotFoundError: /tmp/verify_tmp/refs.json`, unhandled `Traceback` in `verify.py` unrelated to required agent outputs) with no earlier infra or case defects, classify strictly as `verifier` (`VERIFIER_RECOMPUTE_DEFECT`), NEVER `agent` or `unknown`.
- **Check 2 — Causally Bound Parser/Regex Soundness (`failure_binding == "direct"`)**:
  Static parser hazards in `verify.py` (such as Fortran `D+03` exponent omission or namelist `/` truncation) may ONLY be assigned as `primary_root_cause.category = "verifier"` when `failure_binding == "direct"` (i.e., the failing line/field actually failed parsing due to that regex). If `1.23D+03` merely appears as a printed reference number while the agent wrote `9.99E+02`, `failure_binding` is `"none"` and `verifier` must NOT be blamed.
- **Check 3 — Hidden Column/Format Assumptions (`VERIFIER_HIDDEN_CONTRACT`)**:
  If `verify.py` indexes positional `.split()` columns without parsing `Step` header names and `instruction.md` did not specify column order while the agent's `results.json` already passed numerical reference checks, classify as `verifier` (`VERIFIER_HIDDEN_CONTRACT`).

---

## 4. Numerical Attribution & Competing Hypothesis Rules

- **Closed-Loop Numerical Verification**: Numerical trajectory drift requires a strict three-way closed-loop between `instruction.md`, `tests/verify.py`, and `verifier/verify.log`:
  1. **Prompt Contract Verification**: `instruction.md` must be present and must NOT have mandated pointwise exact trajectory reproduction. If `instruction.md` is missing, the contract is incomplete; abstain conservatively to `unknown`.
  2. **Executable Verifier AST Inspection**: `tests/verify.py` must actually assert or compare instantaneous trajectory/coordinates in executable Python AST (`ast.Assert`, `ast.Compare`, or validation calls). Keywords appearing only inside comments (`# trajectory_rmsd`) do not establish a verifier defect; if executable checks are absent, abstain conservatively to `unknown`.
  3. **Runtime Causal Binding**: `verifier/verify.log` must directly bind the failing check to instantaneous trajectory/coordinate RMSD while ensemble averages or conserved quantities agree within tolerance.
  4. When all 3 conditions hold, classify as `verifier` (`VERIFIER_TOLERANCE_TOO_STRICT`).
- **Competing Hypotheses**: Every failed/errored case MUST populate `competing_hypotheses` (`candidate-hypotheses.json`) and `first_unrecovered_deviation`.
- **Calibrated Confidence**: Confidence scores (`confidence_kind = "heuristic_evidence_score"`, `evidence_strength = "high" | "medium" | "low"`) are computed from evidence counts, multi-source corroboration, and competing hypothesis separation (`scripts/confidence.py`).
