# Causal Attribution Protocol

Every failure analysis MUST follow this 7-step backward causal trace protocol. Do not jump from an error log line directly to a root cause label.

## 1. Backward Causal Trace Order

For every failed trial:

1. **Identify the Final Failure Manifestation**
   - What caused the trial to be marked failed (`reward == 0.0` or `exception_info != null`)?
   - Record the exact verifier failure message (`FAIL: ...`) or runner exception (`RuntimeError`, `TimeoutError`).
2. **Trace Backward to the Immediate Artifact State**
   - If `verify.py` failed on a file or value check, inspect how that file/value was produced (or why it is missing).
   - Compare the three-way contract: `instruction.md` (Prompt) vs `tests/verify.py` (Verifier) vs Agent's actions/outputs.
3. **Locate the First Error Decision or Abnormal State**
   - Walk backward through the normalized trajectory events (`trajectory:step:N`) to find where the state first diverged from a valid solution path.
4. **Assess Recoverability**
   - Was the error state recoverable within the container environment (e.g., a missing symlink to `/opt/cp2k/data/`, a non-converged SCF step, or a Python script bug)?
   - Or was it unrecoverable (e.g., container failed to build, pinned asset missing from image, verifier parser bug on valid output)?
5. **Check Agent Observation**
   - Did the agent observe the error message or anomalous value in a tool output?
6. **Check Agent Recovery Actions**
   - Did the agent diagnose the error and adjust parameters/commands appropriately, or did it repeat the failed action / ignore the error / hardcode numbers?
7. **Pinpoint the First Unrecovered Deviation (`first_unrecovered_deviation`)**
   - Record the event ID (`trajectory:step:...` or `runtime:...`) where the trajectory crossed from recoverable to unrecovered failure.

---

## 2. Necessary Gate Conditions for Blaming the Agent

You may assign `primary_root_cause.category = "agent"` **ONLY IF ALL FIVE** of the following conditions hold:

1. **Task Completeness**: `instruction.md` provided sufficient specification, or the required paths/conventions were reasonably discoverable in the container.
2. **Infrastructure Integrity**: `runtime.agent_started == true`, and no fatal container/network/API/timeout failure blocked normal execution.
3. **Verifier Contract Alignment**: The verifier check that failed corresponds to an explicit requirement in `instruction.md` (or a universal physical truth) and is not a verifier parser defect or hidden convention.
4. **Observable Feedback**: The agent had access to observations needed to make the right decision or diagnose the failure.
5. **Causal Link**: Fixing the agent's identified decision/action would directly prevent the final failure manifestation.

> **Hard Rule**: If `runtime.agent_started == false` (e.g., `agent/trajectory.json` is absent and `result.json` shows `environment_setup` failure), `false-agent-blame` is strictly forbidden. The root cause MUST be `infra` (or `case` if the `Dockerfile` itself is broken).

---

## 3. Distinguishing Verifier Defects vs Agent Errors

When `verifier/verify.log` outputs `FAIL: <msg>`:

- **Check 1 — Parser/Regex Soundness**:
  Does `verify.py` parse the agent's input/output file with a brittle regex?
  *Example*: `re.finditer(r"&(\w+)\b(.*?)/", text, re.DOTALL)` truncates namelists at the first `/` inside a string path like `outdir = './outdir'` or `pseudo_dir = '/opt/qe/pseudo'`. If the agent wrote valid QE namelists with `./outdir` and `verify.py` parsed `outdir` as `''`, the primary root cause is `VERIFIER_REGEX_OR_PARSER_DEFECT` (`verifier`), **not** `agent`.
- **Check 2 — Hidden Column/Format Assumptions**:
  Does `verify.py` index positional columns (e.g., `thermo[-1].split()[1]`) assuming a specific `thermo_style custom step pe lx` when `instruction.md` did not mandate that exact `thermo_style` column order, AND the agent's `results.json` already passed the reference numerical tolerance check?
  If `instruction.md` did not specify the exact `thermo_style` column layout, classify as `VERIFIER_HIDDEN_CONTRACT` (`verifier`) or `CASE_AMBIGUOUS_CONTRACT` (`case`), with `agent` as at most a contributing factor.
- **Check 3 — Genuine Agent Post-Processing or Simulation Error**:
  If `instruction.md` explicitly specified the formula, step range (`1000..3000`), or parameter, and the agent's simulation output or `results.json` violated that explicit requirement (e.g., `final_pe` differs from deterministic reference because the agent modified the potential, reset timestep, or used wrong ensemble), classify as `agent`.

---

## 4. Competing Hypothesis Evaluation & Multi-Label Rules

- Generate at least 2 competing hypotheses (`H1`, `H2`, ...) for every non-trivial failure.
- Each hypothesis must list `evidence_for`, `evidence_against`, `missing_evidence`, and `counterfactual_test`.
- Assign **exactly one** `primary_root_cause` and optional `contributing_factors[]`.
- If the top hypotheses cannot be separated with confidence $\ge 0.50$, output `primary_root_cause.category = "unknown"` (`UNKNOWN_INSUFFICIENT_EVIDENCE`).
