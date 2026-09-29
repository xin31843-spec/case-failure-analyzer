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

## 2. Necessary Gate Conditions for Blaming the Agent

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
  If `verify.py` crashes on its own internal paths/files (e.g., `FileNotFoundError: /tmp/verify_tmp/refs.json`, unhandled `Traceback` in `verify.py` unrelated to required agent outputs), classify as `verifier` (`VERIFIER_RECOMPUTE_DEFECT`), NEVER `agent`.
- **Check 2 — Causally Bound Parser/Regex Soundness (`failure_binding == "direct"`)**:
  Static parser hazards in `verify.py` (such as Fortran `D+03` exponent omission or namelist `/` truncation) may ONLY be assigned as `primary_root_cause.category = "verifier"` when `failure_binding == "direct"` (i.e., the failing line/field actually failed parsing due to that regex). If `1.23D+03` merely appears as a printed reference number while the agent wrote `9.99E+02`, `failure_binding` is `"none"` and `verifier` must NOT be blamed.
- **Check 3 — Hidden Column/Format Assumptions (`VERIFIER_HIDDEN_CONTRACT`)**:
  If `verify.py` indexes positional `.split()` columns without parsing `Step` header names and `instruction.md` did not specify column order while the agent's `results.json` already passed numerical reference checks, classify as `verifier` (`VERIFIER_HIDDEN_CONTRACT`).

---

## 4. Numerical Attribution & Competing Hypothesis Rules

- **Structured Numerical Evidence Required**: When structured pointwise trajectory divergence occurs alongside matching ensemble averages or conserved quantities, classify as `verifier` (`VERIFIER_TOLERANCE_TOO_STRICT`), not `agent`. Never classify from a bare keyword like `chaotic` without structured comparison (abstains to `unknown`).
- **Competing Hypotheses**: Every failed/errored case MUST populate `competing_hypotheses` (`candidate-hypotheses.json`) and `first_unrecovered_deviation`.
- **Calibrated Confidence**: Confidence scores (`confidence_kind = "heuristic_evidence_score"`, `evidence_strength = "high" | "medium" | "low"`) are computed from evidence counts, multi-source corroboration, and competing hypothesis separation (`scripts/confidence.py`).
