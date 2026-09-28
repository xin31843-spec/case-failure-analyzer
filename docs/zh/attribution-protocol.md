# 逆向因果归因协议 (`Causal Attribution Protocol`)

**[English](../en/attribution-protocol.md) | [简体中文](attribution-protocol.md)**

每次失败因果审计都必须遵循以下 7 步逆向因果追踪协议，严禁从单行错误日志直接跳向根因结论。

---

## 1. 逆向因果追踪七步法 (`Backward Causal Trace Order`)

针对每一个失败的 Trial：

1. **识别最终失败表象 (`Identify the Final Failure Manifestation`)**
   - 确认导致该 Trial 被判失败的确切表象（`reward < 1.0`、`verify.log` 中的 `FAIL: ...` 或 `exception_info != null`）。
   - 注意：若 `reward >= 1.0`（`verification_status == "passed"`），则该 Trial 已通过，**绝不**因 Job 级错误统计 `stats.n_errored_trials` 污染该 Trial。
2. **回溯直接产物状态 (`Trace Backward to the Immediate Artifact State`)**
   - 检查缺失或无效文件/数值是如何产生的，核查三方契约矩阵：`instruction.md`（Prompt 要求） vs `tests/verify.py`（评测器要求） vs Agent 实际产物。
3. **定位首次错误决策或异常状态 (`Locate the First Error Decision or Abnormal State`)**
   - 沿标准化轨迹事件（`trajectory:step:N`）逆向回溯，找到状态首次偏离合法求解路径的位置。
4. **评估可恢复性 (`Assess Recoverability`)**
   - 区分容器内可由 Agent 自主恢复的问题与不可恢复的外部/环境缺陷（如容器构建失败、题目缺失资产文件、或完成因果绑定的评测器解析缺陷/内部崩溃）。
5. **核查 Agent 观测状态 (`Check Agent Observation`)**
   - 检查 Agent 是否在工具输出（`observation`）中观测到了报错信息或异常数值。
6. **核查 Agent 恢复动作 (`Check Agent Recovery Actions`)**
   - 检查 Agent 是否诊断了错误并合理调整了物理/计算参数，还是未做实质修改就重复执行失败动作（`repeated_failed_action`）或直接忽略错误。
7. **锁定首次不可恢复偏离点 (`first_unrecovered_deviation`)**
   - 记录 `{"status": "identified", "event_ref": "<valid_id>", "summary": "..."}`；若因日志缺失无法定位，显式记录 `{"status": "not_identified", "event_ref": null, "summary": "..."}`。

---

## 2. 归因 Agent 的五大必要条件与硬规则 (`Necessary Gate Conditions for Blaming the Agent`)

仅当以下 **5 项必要条件全部成立** 且存在至少一项 **Agent 正面证据** 时，才允许将 `primary_root_cause.category` 判为 `"agent"`：

1. **任务完备性 (`Task Completeness`)**：`instruction.md` 提供了完整明确的规范说明，且所需资产文件在容器内真实存在。
2. **基础设施完整性 (`Infrastructure Integrity`)**：`runtime.agent_started == true`，且没有任何致命的容器/网络/API/超时故障阻断正常执行。
3. **评测器契约一致性 (`Verifier Contract Alignment`)**：失败的评测检查对应 `instruction.md` 的显式要求，既不是已完成因果绑定的解析器缺陷（`failure_binding == "direct"`），也不是评测器自身崩溃（`verifier_internal_crash`）。
4. **Agent 正面证据 (`Positive Agent Evidence`)**：`evidence_refs` 中至少引用了一项明确的 Agent 正面信号（`behavioral_signals`、`agent_mismatch` 契约违约、Agent 轨迹决策事件、或由 Agent 操作引发的 `scientific_observations`）。仅有 `reward=0` 或 `verify.log` 中的 `FAIL` **不构成**充分证据。
5. **因果闭环 (`Causal Link`)**：修正所定位的 Agent 决策或操作即可直接消除最终失败表象。

> **启动前失败硬规则 (`runtime.agent_started == false`)**：
> - 若 `runtime.agent_started == false` 且存在致命基础设施故障证据（`causal_candidate == true`）→ `primary_root_cause.category` **必须**为 `infra`（若系题目 `Dockerfile` 自身语法/配置损坏则为 `case`）。
> - 若 `runtime.agent_started == false` 且无任何基础设施或异常日志 → `primary_root_cause.category` **必须**为 `unknown` (`UNKNOWN_INSUFFICIENT_EVIDENCE`)。
> - 只要 `runtime.agent_started == false`，将 `primary_root_cause.category` 判为 `"agent"`（误判归因 Agent）属于**绝对禁止行为**。

---

## 3. 区分评测器缺陷与 Agent 错误 (`Distinguishing Verifier Defects vs Agent Errors`)

当 `verifier/verify.log` 输出报错或 `FAIL: <msg>` 时：

- **检查 1 — 评测器内部崩溃 (`VERIFIER_RECOMPUTE_DEFECT`)**：
  若 `verify.py` 因自身内部路径或文件缺失崩溃（例如 `FileNotFoundError: /tmp/verify_tmp/refs.json`、或与 Agent 必选产物无关的未捕获 `Traceback`），必须归因为 `verifier` (`VERIFIER_RECOMPUTE_DEFECT`)，**严禁**判为 `agent`。
- **检查 2 — 完成因果绑定的解析器/正则缺陷 (`failure_binding == "direct"`)**：
  `verify.py` 中的静态解析风险（如未支持 Fortran `D+03` 指数或 namelist 字符串中的 `/` 截断）**仅在** `failure_binding == "direct"`（即失败字段确实因该正则/解析器而解析失败）时才可判为 `verifier`。若 `1.23D+03` 仅作为参考值打印在日志中而 Agent 实际输出了错误数值 `9.99E+02`，则 `failure_binding` 为 `"none"`，不得归咎于 `verifier`。
- **检查 3 — 隐式列序或格式假设 (`VERIFIER_HIDDEN_CONTRACT`)**：
  若 `verify.py` 不解析 `Step` 表头名称而直接按 `.split()` 固定下标取列，且 `instruction.md` 未规定热力学输出列顺序、同时 Agent 的 `results.json` 已通过参考值核验，则应归因为 `verifier` (`VERIFIER_HIDDEN_CONTRACT`)。

---

## 4. 数值漂移与竞争假设规则 (`Numerical Attribution & Competing Hypothesis Rules`)

- **结构化数值证据要求**：严禁仅凭日志中出现 `chaotic` 等单一词汇就判为 `numerical` (`NUMERICAL_TRAJECTORY_DIVERGENCE`)。必须具备结构化对比证据，表明逐点轨迹/瞬时坐标发散的同时，系综统计均值或守恒量与参考值一致。
- **竞争假设必填**：每一个失败或异常用例都必须填充 `competing_hypotheses`（对应 `candidate-hypotheses.json`）及 `first_unrecovered_deviation`。
- **校准的证据强度评分**：置信度评分（`confidence_kind = "heuristic_evidence_score"`，`evidence_strength = "high" | "medium" | "low"`）由支持证据点数、多源交叉印证及竞争假设区分度确定性计算得出（见 `scripts/confidence.py`）。
