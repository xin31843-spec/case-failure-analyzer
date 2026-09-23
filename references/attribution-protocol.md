# Causal Attribution Protocol / 因果归因协议 (中英双版)

Every failure analysis MUST follow this 7-step backward causal trace protocol. Do not jump from an error log line directly to a root cause label.
每次失败因果审计都必须遵循以下 7 步逆向因果追踪协议，严禁从单行错误日志直接跳向根因结论。

---

## 1. Backward Causal Trace Order / 逆向因果追踪步骤

For every failed trial / 针对每一个失败的 Trial：

1. **Identify the Final Failure Manifestation (识别最终失败表象)**
   - What caused the trial to be marked failed (`reward < 1.0` or `exception_info != null`)? Note: If `reward >= 1.0` (`verification_status == "passed"`), the trial passed and must NEVER be polluted by job-level `stats.n_errored_trials`.
   - 记录导致该 Trial 被判失败的确切表象（`verify.log` 中的 `FAIL: ...` 或 runner 异常）。若 `reward >= 1.0`，该 Trial 已通过，绝不因 Job 级错误统计污染该 Trial。
2. **Trace Backward to the Immediate Artifact State (回溯直接产物状态)**
   - Inspect how the missing/invalid file or value was produced and compare the three-way contract: `instruction.md` (Prompt) vs `tests/verify.py` (Verifier) vs Agent's outputs.
   - 核查三方契约矩阵：`instruction.md`（Prompt 要求） vs `tests/verify.py`（评测器要求） vs Agent 实际产物。
3. **Locate the First Error Decision or Abnormal State (定位首次错误决策或异常状态)**
   - Walk backward through normalized trajectory events (`trajectory:step:N`) to find where the state first diverged from a valid solution path.
4. **Assess Recoverability (评估可恢复性)**
   - Distinguish recoverable container-side issues from unrecoverable defects (e.g., container build failure, missing task asset, or causally bound verifier parser/internal crash).
5. **Check Agent Observation (核查 Agent 观测状态)**
   - Did the agent observe the error message or anomalous value in a tool output?
6. **Check Agent Recovery Actions (核查 Agent 恢复动作)**
   - Did the agent diagnose the error and adjust parameters appropriately, or did it repeat the failed action (`repeated_failed_action`) / ignore the error?
7. **Pinpoint the First Unrecovered Deviation (`first_unrecovered_deviation` / 锁定首次不可恢复偏离点)**
   - Record `{"status": "identified", "event_ref": "<valid_id>", "summary": "..."}` or `{"status": "not_identified", "event_ref": null, "summary": "..."}` when logs are incomplete.

---

## 2. Necessary Gate Conditions for Blaming the Agent / 归因 Agent 的五大必要条件与硬规则

You may assign `primary_root_cause.category = "agent"` **ONLY IF ALL FIVE** of the following conditions hold (plus at least one positive agent evidence reference):
仅当以下 **5 项必要条件全部成立** 且存在至少一项 **Agent 正面证据** 时，才允许将主根因判为 `agent`：

1. **Task Completeness (任务完备性)**: `instruction.md` provided sufficient specification, and required assets exist in the container.
2. **Infrastructure Integrity (基础设施完整性)**: `runtime.agent_started == true`, and no fatal container/network/API/timeout failure blocked normal execution.
3. **Verifier Contract Alignment (评测器契约一致性)**: The failing verifier check corresponds to an explicit requirement in `instruction.md` and is neither a causally bound verifier parser defect (`failure_binding == "direct"`) nor a verifier internal crash (`verifier_internal_crash`).
4. **Positive Agent Evidence (Agent 正面证据)**: At least one positive agent signal is cited in `evidence_refs` (`behavioral_signals`, `agent_mismatch` contract, agent trajectory decision event, or agent-caused `scientific_observations`). Bare `reward=0` or `FAIL` in `verify.log` is NOT sufficient.
5. **Causal Link (因果闭环)**: Fixing the agent's identified decision/action would directly prevent the final failure manifestation.

> **Hard Rule on Pre-Startup Failures (`runtime.agent_started == false` / 未启动硬规则)**:
> - If `runtime.agent_started == false` AND fatal infrastructure evidence exists (`causal_candidate == true`) -> `primary_root_cause.category` MUST be `infra` (or `case` if the `Dockerfile` itself is broken).
> - If `runtime.agent_started == false` AND no infrastructure or exception logs exist -> `primary_root_cause.category` MUST be `unknown` (`UNKNOWN_INSUFFICIENT_EVIDENCE`).
> - Whenever `runtime.agent_started == false`, attributing `primary_root_cause.category = "agent"` (`false-agent-blame`) is **strictly forbidden**.

---

## 3. Distinguishing Verifier Defects vs Agent Errors / 区分评测器缺陷与 Agent 错误

When `verifier/verify.log` outputs an error or `FAIL: <msg>`:

- **Check 1 — Verifier Internal Crash (`VERIFIER_RECOMPUTE_DEFECT`)**:
  If `verify.py` crashes on its own internal paths/files (e.g., `FileNotFoundError: /tmp/verify_tmp/refs.json`, unhandled `Traceback` in `verify.py` unrelated to required agent outputs), classify as `verifier` (`VERIFIER_RECOMPUTE_DEFECT`), NEVER `agent`.
  若 `verify.py` 因自身临时文件或参考文件缺失崩溃，必须判为 `verifier` (`VERIFIER_RECOMPUTE_DEFECT`)，严禁判为 `agent`。
- **Check 2 — Causally Bound Parser/Regex Soundness (`failure_binding == "direct"`)**:
  Static parser hazards in `verify.py` (such as Fortran `D+03` exponent omission or namelist `/` truncation) may ONLY be assigned as `primary_root_cause.category = "verifier"` when `failure_binding == "direct"` (i.e., the failing line/field actually failed parsing due to that regex). If `1.23D+03` merely appears as a printed reference number while the agent wrote `9.99E+02`, `failure_binding` is `"none"` and `verifier` must NOT be blamed.
- **Check 3 — Hidden Column/Format Assumptions (`VERIFIER_HIDDEN_CONTRACT`)**:
  If `verify.py` indexes positional `.split()` columns without parsing `Step` header names and `instruction.md` did not specify column order while the agent's `results.json` already passed numerical reference checks, classify as `verifier` (`VERIFIER_HIDDEN_CONTRACT`).

---

## 4. Numerical Attribution & Competing Hypothesis Rules / 数值漂移与竞争假设规则

- **Structured Numerical Evidence Required (`结构化数值证据要求`)**: Never classify as `numerical` (`NUMERICAL_TRAJECTORY_DIVERGENCE`) from a bare keyword like `chaotic`. Require structured comparison showing pointwise trajectory/position divergence alongside matching ensemble averages or conserved quantities.
- **Competing Hypotheses (`竞争假设`)**: Every failed/errored case MUST populate `competing_hypotheses` (`candidate-hypotheses.json`) and `first_unrecovered_deviation`.
- **Calibrated Confidence (`启发式证据强度评分`)**: Confidence scores (`confidence_kind = "heuristic_evidence_score"`, `evidence_strength = "high" | "medium" | "low"`) are computed from evidence counts, multi-source corroboration, and competing hypothesis separation (`scripts/confidence.py`).
