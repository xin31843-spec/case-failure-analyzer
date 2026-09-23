# Case-Failure-Analyzer 项目分析报告

- **分析对象**: `/Users/hx/workspace/ccb-run/Case-Failure-Analyzer`
- **分析日期**: 2026-09-23
- **分析方式**: 全量源码阅读 + 14 个现有单测复跑 + 12 组定向复现实验（构造 job/task 目录，观测实际输出）
- **代码规模**: Python 8 个模块 3,195 行 + 参考文档 11 份 500 行 + 单测 5 个文件 545 行
- **总体结论**: 架构分层清晰、文档规范完备，但**归因引擎的实际行为与文档承诺存在系统性偏离**；存在 2 个会产生错误结论的 P0 缺陷，以及 5 个会导致错误归因的 P1 缺陷。当前实现更接近"关键词匹配决策树"，而非文档所描述的"证据优先的因果推理器"。

---

## 1. 项目定位与架构

### 1.1 定位

这是一个 Claude Code Skill 包（`SKILL.md` + `scripts/` + `references/`），用于诊断科学计算基准测试（CP2K / Quantum ESPRESSO / LAMMPS / xTB / ASE / RDKit）用例失败的根本原因，输出结构化归因 `analysis.json` 与人类可读 `report.md`。

其自我声明的核心价值主张（`SKILL.md:10-11`）是：**"执行端到端的、有证据支撑的因果审计，而非朴素的关键词匹配日志搜索"**。

### 1.2 目录结构

| 路径 | 内容 | 评价 |
|---|---|---|
| `SKILL.md` | 技能入口，6 步工作流 + 7 条硬性归因约束 | 规范清晰 |
| `agents/openai.yaml` | 元数据（version 1.0.0, entrypoint, capability 声明） | 命名 `openai.yaml` 对 Claude Skill 包略显突兀 |
| `scripts/` | 8 个 Python 模块，2,195 行 | 分层合理，见 1.3 |
| `references/` | taxonomy / attribution-protocol / evidence-schema / report-schema / skill-prescription-policy | 5 份元规范 + 6 份软件知识库，质量较高 |
| `tests/` | 5 个测试文件，14 个用例（含 7 个"金标准用例"） | 全部通过，但固化了部分缺陷（见 §4.5） |

### 1.3 数据流

```
discover_artifacts.py    →  artifacts / runtime 状态门控 (agent_started, verifier_started)
        ↓
normalize_trajectory.py  →  ATIF-v1.7 时间线 + behavioral_signals
        ↓
extract_runtime_errors.py→  INFRA_* 错误观测（区分 causal_candidate / transient）
        ↓
audit_contract.py        →  Prompt ↔ Verifier ↔ Agent 三方契约矩阵 + parser hazard 静态扫描
        ↓
extract_scientific_errors.py → 6 款软件的 error_family 适配器
        ↓
analyze_case.py::build_causal_attribution  →  analysis.json（5 道 Gate 顺序判定）
        ↓
validate_analysis.py     →  模式校验 + 3 条硬性约束
        ↓
render_report.py         →  report.md（11 个必备章节）+ skill-prescription.md
```

**设计优点**（应当在重构中保留）：

- 五阶段职责分离干净，每个 `scripts/*.py` 均可独立 CLI 调用，便于单测与调试。
- `evidence.json`（客观观测）与 `analysis.json`（主观归因）严格分离 —— 这是正确的证据链设计。
- 所有证据都带 `source_file` + `source_pointer`（JSON Pointer / 行号），可回溯。
- `causal_candidate` vs `transient` 的区分（`extract_runtime_errors.py:264-273`）是真正有价值的设计：同一句 `Failed to fetch` 在"构建期致命"与"运行期重试成功"两种语境下结论相反。
- `_ds_store` 之外，参考文档质量高，`taxonomy.md` 的 category/subtype/code 三级编码体系设计得当。

---

## 2. 验证方法与复现矩阵

分析的每一条结论都通过构造最小 `jobs/` + `tasks/` 目录树并调用真实入口脚本复现。所有实验均可重跑：

| # | 复现目标 | 复现方式 | 结果 |
|---|---|---|---|
| 1 | 通过用例是否被正确识别 | job 含 2 trial（1 失败 1 reward=1.0），`result.json` 含 `stats.n_errored_trials=1` | ❌ reward=1.0 被报为 `errored`/`failed` |
| 2 | 关键词是否唯一定根因 | verify.log 含无上下文的单词 `chaotic` | ❌ 判为 `numerical` @0.86 |
| 3 | verifier 是否会被误伤 | agent 写错数值，verifier 日志引用 `1.23D+03` 参考值 | ❌ 判为 `verifier` @0.92 |
| 4 | verifier 自身崩溃归属 | verify.log 为 `FileNotFoundError: /tmp/verify_tmp/refs.json` | ❌ 判为 `agent` @0.85 |
| 5 | 双真值源是否一致 | 仅存在 `agent/claude-code.txt` 的 trial | ❌ discover=True / extract=False |
| 6 | `stats: null` 健壮性 | `result.json` 中 `{"stats": null}` | ❌ `AttributeError` 崩溃 |
| 7 | 硬规则 #3 是否被遵守 | 复现 gold case 7（agent 未启动） | ❌ 输出 `unknown`，非文档要求的 `infra` |
| 8 | 校验器是否强制竞争假设 | 提交缺 `competing_hypotheses` 与 `first_unrecovered_deviation` 的 analysis | ❌ 校验通过 |
| 9 | report 章节校验强度 | 提交仅含 11 个章节名的单行文本作为 report.md | ❌ 校验通过 |
| 10 | `--replay verifier` 是否真的重放 | CLI 实跑 | ❌ 仅写入一条指向已删除临时目录的记录 |
| 11 | `--replay safe` 是否可用 | CLI 实跑 | ❌ 静默无操作 |
| 12 | 知识库命名对齐率 | 程序化比对适配器 vs 文档 error_family | ❌ 37 个文档族群仅 10 个（27%）可用于匹配 |

---

## 3. P0 级缺陷（产生错误结论）

### 3.1 通过用例被误报为失败：作业级统计量污染每个 trial

**位置**: `scripts/discover_artifacts.py:266` 与 `:268-277`

```python
n_errored = job_result.get("stats", {}).get("n_errored_trials", 0)   # ← 作业(job)级统计量

if exc_info is not None or n_errored > 0 or (trial_dir and (trial_dir / "exception.txt").is_file()):
    exit_status = "errored"          # ← 却用于判定单个 trial
elif reward_val is not None and reward_val >= 1.0:
    exit_status = "completed"
```

`n_errored_trials` 是整个 job 的汇总计数，却被无条件应用于该 job 下**每一个** trial 的 `exit_status`。只要 job 里有任意一个 trial 出错，所有 trial 的 `exit_status` 都会变成 `errored`，`reward >= 1.0` 的分支成为死代码。

**实测**（复现 #1）：

```
trial_A   exit_status=errored    reward=None     ← 正确
trial_B   exit_status=errored    reward=1.0      ← 错误，应为 completed
```

**级联影响**：`analyze_case.py:77` 的"用例已通过"分支 `if exit_status == "completed" and reward >= 1.0:` 永不触发，于是这个 reward=1.0 的 trial 继续向下走完 5 道 Gate，最终落到 Gate 5 兜底分支，输出：

```
verdict       : failed
category/code : unknown / UNKNOWN_INSUFFICIENT_EVIDENCE
manifestation : Trial failed without trajectory events, verifier logs, or exception tracebacks.
```

一个明确通过的用例被报告为"失败/证据不足"。这直接破坏该工具最基础的输出可信度。

**修复**：`exit_status` 判定必须完全基于 trial 级证据（`trial_result["exception_info"]`、trial 级 `exception.txt`、trial 级 `reward`）；job 级统计量只应写入 `metadata`，不参与判定。

### 3.2 Gate 5 兜底即指责 Agent；`unknown` 在 Agent 启动后不可达

**位置**: `analyze_case.py:477-509`（unknown 分支）与 `:610-615`（兜底分支）

5 道 Gate 是纯排他链：Gate 1 未启动 → Gate 2 case 缺陷 → Gate 3 verifier 缺陷 → Gate 4 数值发散 → **Gate 5 一律归因 agent**。`unknown` 分支的唯一进入条件是：

```python
if not timeline and not fail_text and not sci_obs:
```

即"无时间线 **且** 无verifier日志 **且** 无科学错误观测"。一旦 agent 启动（产生 timeline）且 verifier 留下任意一行日志，`unknown` 就从结构上不可达，**必然**落到 `analyze_case.py:610-615`：

```python
else:
    subtype = "result_validation"
    code = "AGENT_RESULT_VALIDATION"
    summary = f"Agent completed execution but output failed verification: {fail_text[:200]}"
```

**实测**（复现 #4）：一个 verifier 因自身临时目录缺失而崩溃的场景（taxonomy 中明确定义为 `VERIFIER_RECOMPUTE_DEFECT`），被判定为 `agent` @0.85。

这直接违反该项目自己写下的两条规则：

- `SKILL.md:60` — "证据无法区分竞争假设时使用 `unknown`"
- `attribution-protocol.md §4` — "若最高两个假设无法以置信度 ≥ 0.50 分离，输出 `unknown`"

**修复**：Gate 5 必须拆分——先判断是否存在**指向 agent 的正面证据**（如 `repeated_failed_action`、`scientific_parameter_changed` 且有对应替代方案），无正面证据时落入 `unknown`，而不是把"没有其他解释"当作"是 agent 的错"。

---

## 4. P1 级缺陷（导致错误归因）

### 4.1 关键词直接定根因（违反自身 Hard Rule #1）

**位置**: `analyze_case.py:423`

```python
if re.search(r"(?:trajectory_rmsd|instantaneous_position|chaotic|ensemble average matches)", fail_text, re.IGNORECASE):
```

`chaotic` 是一个普通英文词。任何 verifier 日志里出现该词，都会以 **0.86 置信度**输出 `NUMERICAL_TRAJECTORY_DIVERGENCE`，且 `competing_hypotheses` 为空数组。

**实测**（复现 #2）：verify.log 内容为 `FAIL: agent output absent; protocol note mentions chaotic behaviour of the reference run` →

```
numerical / NUMERICAL_TRAJECTORY_DIVERGENCE @0.86   hypotheses: 0
```

这里既没有轨迹数据，也没有任何数值对比。`SKILL.md:55` 明写 "Do not classify solely from an error string" —— 该行代码正是如此。

### 4.2 Gate 3 静态 hazard 导致 verifier 假阳性

**位置**: `audit_contract.py:187-196`（静态扫描）+ `:379-382`（触发条件）

Hazard 2 的检测是**纯静态**的：只要 `verify.py` 里出现形如 `[-\d.E+]+` 的正则且未显式包含 `d`，就登记一条 hazard。触发条件则宽松到：

```python
if re.search(r"\d+\.\d+[Dd][+-]\d+", verify_log_text):
    triggered = True
```

即"**日志里任何位置**出现一个 D 记数数字"。一旦触发，`analyze_case.py:305-418` 的 Gate 3 便以 **0.92 置信度**判 verifier 有缺陷，同时把 agent 假设以 "already within tolerance" 的措辞排除。

**实测**（复现 #3）：agent 确实输出了错误数值（`ENERGY: 9.99E+02` vs 参考 `1.23D+03`），仅因参考值以 D 记数打印，得到：

```
verifier / VERIFIER_REGEX_OR_PARSER_DEFECT @0.92
```

**根因**：hazard 与触发条件之间缺少因果绑定——代码没有验证"**失败的那次解析**"用的就是这条正则。正确做法是要求 hazard 对应的正则与失败行号/失败信息直接关联，否则最多只能作为 `competing_hypotheses` 中的一条低置信度假设。

### 4.3 硬规则 #3 自相矛盾，且被测试固化

**文档**（`SKILL.md:57`，`attribution-protocol.md §2` "Hard Rule"）：
> 若 `runtime.agent_started == false`，则 `primary_root_cause.category` **必须**为 `infra`。

**实现**（`analyze_case.py:200-241`）：未启动且无匹配的 INFRA 规则时，输出 `unknown` @0.30。

**实测**（复现 #7，即项目自带的 gold case 7）：

```
agent_started = False
category      = unknown -> UNKNOWN_INSUFFICIENT_EVIDENCE
```

更值得注意的是，`tests/test_report_validation.py:237-249` 的 `test_golden_7_unknown_missing_logs` **断言**了这一行为。也就是说，测试套件把与文档硬规则冲突的行为当成了正确行为加以保护。

这里需要指出：从工程角度看 `unknown` 是**更诚实**的输出，问题出在文档——硬规则写得太绝对。应当修正的是 `SKILL.md` 与 `attribution-protocol.md`（改为"存在可归因的 infra 证据时必须是 infra；无任何证据时为 unknown"），并说明二者的边界。

### 4.4 校验器未强制其规范要求的字段

**位置**: `validate_analysis.py:33-46`（`REQUIRED_ANALYSIS_KEYS`）

`competing_hypotheses` 与 `first_unrecovered_deviation` **均不在必填集合内**，而：

- `evidence-schema.md` 将二者列为 `analysis.json` 的标准字段；
- `attribution-protocol.md §4` 要求"每个非平凡失败至少生成 2 个竞争假设"；
- `report-schema.md` 第 3 章要求 report 展示 `first_unrecovered_deviation`。

同时 `analyze_case.py` 自身在多个分支输出 `"competing_hypotheses": []`（如 Gate 4 的 `:457`、Gate 1-unknown 的 `:225`、passed 分支的 `:98`）。

**实测**（复现 #8）：提交一份**完全不含**这两个字段的 analysis，校验返回 `(True, [])`。

此外 `validate_analysis.py:150-153` 的 report 章节校验是裸子串匹配：

```python
for sec in REQUIRED_REPORT_SECTIONS:
    if sec not in report_text:
```

**实测**（复现 #9）：一份内容仅为 `Executive Summary / Case 状态 / 执行时间线 / ...` 单行文本的 report.md 通过校验。

**修复**：把两个字段加入 `REQUIRED_ANALYSIS_KEYS`；章节校验改为匹配 `^## \d+\. <标题>` 的行首正则。

### 4.5 科学知识库与适配器大面积命名漂移

**位置**: `extract_scientific_errors.py:21-341` vs `references/software/*.md`

`SKILL.md:43` 要求分析者"查阅 `references/software/<software>.md` 获取判别证据要求"。但适配器产出的 `error_family` 名称与文档表格中的名称对不上，程序化比对结果：

| 软件 | 文档族群数 | 实现族群数 | 名称一致（可用于关联） | 实现了但文档无 | 文档有但未实现 |
|---|---|---|---|---|---|
| cp2k | 8 | 5 | 3 | 2 | 5 |
| quantum-espresso | 6 | 4 | 2 | 2 | 4 |
| lammps | 8 | 5 | 2 | 3 | 6 |
| ase | 5 | 2 | 1 | 1 | 4 |
| xtb | 5 | 2 | 2 | 0 | 3 |
| rdkit | 5 | 2 | 0 | 2 | 5 |
| **合计** | **37** | **20** | **10 (27%)** | **10** | **27** |

命名不一致示例：

| 文档名称 | 代码名称 |
|---|---|
| `cholesky_or_overlap_failure` | `cholesky_decomposition_failure` |
| `geoopt_or_cellopt_nonconvergence` | `geoopt_not_converged` |
| `pseudopotential_read_failure` | `pseudopotential_mismatch_or_missing` |
| `prefix_or_outdir_chain_mismatch` | `workflow_prefix_or_outdir_mismatch` |
| `bond_or_topology_missing` | `bond_atoms_missing` |
| `restart_or_timestep_continuation_mismatch` | `restart_continuation_divergence` |
| `thermo_column_or_log_format_mismatch` | `thermo_column_or_ecoh_mismatch` |
| `calculator_not_attached` | `calculator_or_property_error` |
| `smiles_parse_or_none_mol` / `sanitization_or_valence_error` | `smiles_or_sanitization_error` |

**影响**：知识库实际上是**未被连接**的。分析者（人或模型）拿到 `error_family: workflow_prefix_or_outdir_mismatch` 后，无法在 `quantum-espresso.md` 中定位对应行。而 27 个已文档化的高价值族群（如 `md_abnormal_termination`、`mpi_or_runtime_crash`、`ecut_or_kpoint_misconfiguration`、`neighbor_list_overflow`、`stereochemistry_or_canonicalization_mismatch`）**完全没有实现**，等于文档白写。

**修复**：将 `error_family` 提升为共享常量（单一真值源），由文档与代码同时引用；对未实现族群明确标注 `status: documented-only`。

### 4.6 双真值源：`agent_started` 在两处独立计算且可分歧

**位置**: `discover_artifacts.py:252-263` vs `extract_runtime_errors.py:168-177`

两处各自实现 `agent_started` / `verifier_started`，但判据集合不同（前者额外认 `agent/claude-code.txt`（非空）与 `verifier/reward.txt`，后者不认）。

**实测**（复现 #5）：

```
discover.agent_started      : True
extract.agent_started       : False
causal INFRA codes          : ['INFRA_EXTERNAL_NETWORK']
```

于是写入 `evidence.json` 的状态自相矛盾：`runtime.agent_started = true`，但 `error_observations` 声称一条构建期网络错误 `causal_candidate = true`（该标记的语义正是"因为 agent 没启动，所以这条错误是致命的"）。下游 Gate 1 用的是前者，因此跳过 infra 归因，但错误观测又声称 infra 致命。

**修复**：把 runtime 状态门控提取为一个共享函数（如 `runtime_state.py::compute_stage_gates()`），两个阶段共用同一真值源。

### 4.7 `--replay` 是空壳

**位置**: `analyze_case.py:41-53`、`:732-735`、`:784-788`

- `run_isolated_verifier_replay()` 只创建一个 `tempfile.TemporaryDirectory()`，**立即退出上下文管理器**（目录被删除），然后返回一条字符串"Isolated verifier check recorded"。函数名与返回值都声称做了隔离重放，实际**没有执行任何校验**。
- `--replay safe` 在 argparse 中是可选项，但 `analyze_single_trial` 仅判断 `replay_mode == "verifier"`，因此 `safe` **静默无操作**——没有任何警告或错误。

**实测**（复现 #10/#11）：

```
--replay verifier → replay.isolated_dir = /var/.../cfa_replay_t4od_qmr   (still exists: False)
--replay safe     → replay field: None
```

同时 `SKILL.md:22` 明确承诺 "Does not run expensive DFT/MD simulations unless `--replay safe` is explicitly requested"，即 `safe` 模式被描述为存在且有语义。

记录的临时目录路径在 `evidence.json` 落盘时已经不存在，属于悬空引用，会误导下游消费者。**修复**：要么实现真实重放，要么移除 `safe` 选项并把 `verifier` 重放改名为 `dry-run-mark` 之类的诚实命名。

### 4.8 置信度是常量而非证据的函数

对 `scripts/` 的硬编码置信度统计：

| 常量 | 出现次数 | 用于 |
|---|---|---|
| 1.00 / 0.98 | 各 1 / 2 | 已通过 / infra 未启动 |
| 0.95 | 2 | case 缺资产 |
| 0.92 | 2 | verifier 缺陷 |
| 0.90 | 1 | 伴随 infra 因素 |
| 0.86 | 1 | 数值发散 |
| 0.85 | 2 | **agent 兜底** |
| 0.65 / 0.70 | 各 1 | case 契约模糊 / verifier 容差过严 |
| 0.30 / 0.31 | 各 1 | unknown |

这些数值不随证据强度变化：无论有 1 条还是 20 条佐证、无论佐证是否互相印证，输出都是同一个数。**0.98 ≈ 确定性**，但 Gate 1 的触发条件只是一条正则命中。`evidence-schema.md` 把 `confidence` 定义为分析者的校准输出，当前实现使其失去信息量。

**建议**：要么基于证据计数/一致性计算，要么在文档中明确声明"这些是策略常量，不是概率校准值"，避免下游把 0.98 当统计置信度使用。

### 4.9 引擎内嵌案例专属知识（过拟合迹象）

`build_causal_attribution` 是 628 行的条件链（占 `analyze_case.py` 的 75%），其中包含明显来自具体失败案例的硬编码文本，而非通用规则：

- `analyze_case.py:404-416` — 直接写明修复方案 "replace non-greedy namelist `/` regex with quote-aware namelist parsing, support `D/d` scientific notation exponents, and parse `Step ...` thermo header names"。
- `analyze_case.py:576-600` — 完整内嵌 `lammps-deterministic-restart-continuation` 技能处方，包含 `read_restart`、`reset_timestep`、`fix nve` 等具体指导。
- `audit_contract.py:199-209` — Hazard 3 的检测条件要求源码中**同时**存在字面量 `thermo[-1].split()` 和变量名 `last_pe`，这是对某一个具体 `verify.py` 的指纹匹配，换个变量名即失效。
- `analyze_case.py:410` — 建议动作中直接写死 "hardcoding column index `1`"。

**影响**：这些规则对"已被观测过的那几个案例"精确有效（故 7 个 golden test 全绿），但对新案例的泛化能力未经检验，且违反了 `skill-prescription-policy.md §1.2` 自己要求的"非一次性补丁"原则。

---

## 5. P2 级缺陷（健壮性与工程）

| # | 问题 | 位置 | 说明 |
|---|---|---|---|
| 1 | `stats: null` 导致崩溃 | `discover_artifacts.py:266` | `job_result.get("stats", {})` 对显式 `null` 返回 `None`，随后 `.get()` 抛 `AttributeError`。实测（复现 #6）：未捕获异常，整个分析中断。应改为 `(job_result.get("stats") or {})` |
| 2 | 悬空临时目录引用 | `analyze_case.py:47-53` | 见 §4.7 |
| 3 | report 措辞与事实不符 | `render_report.py:72` | 无时间线时固定输出"无 Agent 轨迹事件（Agent 启动前已终止或 `agent/trajectory.json` 缺失）"，但当 `agent_started=True` 且轨迹为空 steps 时该表述错误 |
| 4 | `first_unrecovered_deviation.timestamp` 常为 null | `analyze_case.py:137` 等多处 | 取 `runtime.started_at`，而该值在多数 trial 级 `result.json` 中不存在；实测 report 输出 `(N/A)` |
| 5 | Markdown 表格未全面转义 | `render_report.py:107, 121` | 仅对 `command` / `details` 转义 `\|`，`item`、`prompt_requirement` 等字段直接插入，含 `\|` 时破坏表格 |
| 6 | 时间线截断丢弃关键事件 | `render_report.py:63` | 硬截断 `timeline[:25]`，未保证 `first_unrecovered_deviation` 指向的事件被包含 |
| 7 | 轨迹文件无大小上限 | `normalize_trajectory.py:100` | `json.loads(path.read_text())` 一次性读入内存，无 `max_bytes` 保护（日志类文件有保护，轨迹没有） |
| 8 | 未使用的导入 | `analyze_case.py:20-21` | `shutil`、`subprocess` 导入后从未使用 |
| 9 | 测试目录不可被 unittest 发现 | `tests/` | 缺 `__init__.py`，`python3 -m unittest discover -s tests` 报 `ImportError: Start directory is not importable`；也无 pytest 配置。当前只能逐文件 `python3 tests/xxx.py` 运行 |
| 10 | 仓库卫生 | 根目录 | 无 `README.md`、`requirements.txt`/`pyproject.toml`、CI 配置；`.DS_Store` 出现在根目录与 `tests/`；无 `.gitignore`。脚本依赖均为标准库（这点很好），但未声明 Python 版本要求（`discover_artifacts.py:51` 依赖 3.11+ 的 `tomllib`） |
| 11 | 元数据不一致 | `agents/openai.yaml` | 声明 `supports_atif_version: "ATIF-v1.7"`，但 `normalize_trajectory.py:19` 实际接受 v1.5/v1.6/v1.7；`output_schema: failure-analysis-v1` 与校验器一致，但两个文件各自硬编码，无单一真值源 |
| 12 | job/trial 目录启发式有误判风险 | `discover_artifacts.py:75-85` | 仅凭存在 `agent/`、`verifier/`、`trial.log` 或 `result.json` 含 `trial_name` 就判定为 trial 目录；若 job 目录恰好含 `agent/` 会被整体误判为单个 trial |

---

## 6. 测试与文档评估

### 6.1 测试

**现状**：14 个用例全部通过（已复跑确认）。

```
test_artifact_discovery.py   ..  OK (2 tests)
test_contract_audit.py       .   OK (1 test)
test_report_validation.py    .......  OK (7 tests)
test_runtime_extraction.py   ..  OK (2 tests)
test_trajectory_normalization.py ..  OK (2 tests)
```

**优点**：7 个 golden case 覆盖了 taxonomy 的 7 个主要 category（infra / case / agent×2 / verifier / numerical / unknown），是有意义的行为契约测试。

**问题**：

1. **测试固化了缺陷**：`test_golden_7` 断言 `agent_started=False` 时输出 `unknown`，与 `SKILL.md:57` 的硬规则直接冲突（§4.3）。
2. **无负面测试**：没有任何用例验证"不应归因 agent"的场景（如 verifier 自身崩溃、关键词误触发）。本次分析发现的 P0/P1 缺陷全部位于测试盲区。
3. **无端到端 CLI 测试**：`analyze_case.py::main` 的参数处理、多 trial 输出布局、`--replay`、`--format` 全部未覆盖——`--replay safe` 静默失效因此长期未被发现。
4. **无回归夹具**：`tests/fixtures/` 只有一个 6 行的 JSON 元数据文件（`golden_infra_docker_fail.json`），不含任何真实 job/task 目录树；所有测试都在 `tempfile` 里用代码构造输入。
5. **发现机制损坏**：缺 `__init__.py`，标准 `unittest discover` 不可用。

### 6.2 文档

文档质量整体**高于**其描述的实现，这本身构成问题：文档描述的是一个理想的证据推理器，代码实现的是关键词决策树。

| 文档承诺 | 实现现状 | 差距 |
|---|---|---|
| "非朴素关键词匹配"（`SKILL.md:10`） | Gate 4 用单词 `chaotic` 定根因（§4.1） | 严重 |
| "证据无法区分时输出 unknown"（`SKILL.md:60`） | unknown 在 agent 启动后不可达（§3.2） | 严重 |
| "agent 未启动必须是 infra"（`SKILL.md:57`） | 实现输出 unknown 且测试固化（§4.3） | 严重 |
| "生成 ≥2 个竞争假设"（`attribution-protocol.md §4`） | 多数分支输出空数组，校验器不检查（§4.4） | 中 |
| "查阅 `references/software/*.md`"（`SKILL.md:43`） | 名称对不上，27/37 族群未实现（§4.5） | 中 |
| "`--replay safe` 可按需重算"（`SKILL.md:22`） | 静默无操作（§4.7） | 中 |

另外，`SKILL.md` 描述的工作流（第 2-8 步"重建时间线"、"审计契约"、"评估竞争假设"、"指派主根因"）读起来是**模型**的工作，但 `scripts/analyze_case.py` 作为 `entrypoint` 已经用代码把结论定死了。两种设计（"脚本出结论" vs "模型出结论，脚本只出证据"）在同一份规范中并存，是造成上述偏离的结构性原因——见 §7。

---

## 7. 结构性判断

剥开分层外观，`build_causal_attribution` 的实质是一个 **5 分支排他决策树**：

```
if 未启动:            → infra（或 unknown）
elif 缺资产:          → case
elif 命中 hazard:     → verifier
elif 命中关键词:      → numerical
else:                 → agent（@0.85，无正面证据要求）
```

这与该 Skill 自我宣称的"竞争假设评估 → 证据裁决 → 校准不确定性"方法论是两套不同的东西。具体表现：

1. **无假设竞争机制**。`competing_hypotheses` 是每个 Gate 里手写的装饰性数组，不是"生成候选 → 逐条用证据检验 → 淘汰"的产物。Gate 3 的 H2（agent）在证据栏里被直接写成"already within tolerance"，即结论先行。
2. **无不确定性表达**。分歧场景（如"日志里出现 D 记数但可能与该正则无关"）没有中间态输出，只有 0.92 或 0.85 这样事先写好的数字。
3. **Gate 顺序即优先级，且不可回退**。Gate 2（case）无条件优先于 Gate 3（verifier）——即使缺资产与解析缺陷同时存在、且下游缺陷才是实际拦截点，也不会体现在结论里（本次实测 out/report.md 即为此情形：日志清楚显示解析失败，结论却只有缺资产）。
4. **知识层未接入**。6 份软件知识库（86 行）与 `SCIENTIFIC_ADAPTERS` 之间靠字符串名对齐，实际对齐率 27%（§4.5），知识库在归因路径上基本不起作用。

**这不是"代码写得不好"，而是规范与实现的目标不一致**：`SKILL.md` 描述的是给模型用的推理流程（脚本提供 `evidence.json`，模型产出 `analysis.json`），而 `analyze_case.py` 把两者都做完了并写死。只要这个二义性存在，`evidence-schema.md` 里"evidence.json 不得包含主观根因标签"与"analysis.json 由脚本生成"就会持续互相拉扯。

---

## 8. 改进建议

### 8.1 必须修复（正确性）

| 优先级 | 动作 | 涉及位置 |
|---|---|---|
| P0 | `exit_status` 判定改为纯 trial 级证据，job 统计量退出判定逻辑 | `discover_artifacts.py:265-277` |
| P0 | Gate 5 拆为"有正面 agent 证据 → agent"与"否则 → unknown" | `analyze_case.py:610-615` |
| P0 | 删除 Gate 4 的裸关键词触发，改为要求结构化证据（轨迹/能量序列/容差对比） | `analyze_case.py:423` |
| P1 | Hazard 触发必须与失败解析行绑定；否则降级为低置信度竞争假设 | `audit_contract.py:379-394` |
| P1 | 统一 `agent_started` / `verifier_started` 真值源 | `discover_artifacts.py:252-263` + `extract_runtime_errors.py:168-184` |
| P1 | 把 `competing_hypotheses`、`first_unrecovered_deviation` 加入必填校验；report 章节改行首正则 | `validate_analysis.py:33-46, 150-153` |
| P2 | `n_errored = (job_result.get("stats") or {}).get(...)` | `discover_artifacts.py:266` |

### 8.2 必须澄清（规范一致性）

1. **决定架构归属**：是"脚本出证据 + 模型出结论"，还是"脚本出结论"？
   - 若选前者：`analyze_case.py` 应止步于 `evidence.json`，`analysis.json` 由模型按 `attribution-protocol.md` 产出，`validate_analysis.py` 作为模型的约束闸门（这正是当前校验器的设计定位，只是被脚本抢跑了）。
   - 若选后者：需从 `SKILL.md` 删除第 2-8 步的模型推理描述，并把 `attribution-protocol.md` 改写为算法规格。
2. **修正硬规则 #3**：改为"有 infra 证据时必须 infra；无证据时 unknown"，并同步更新 `SKILL.md:57`、`attribution-protocol.md §2` 与 `test_golden_7`。
3. **诚实标注 `confidence`**：说明它是策略常量而非概率校准。
4. **`--replay` 二选一**：实现真重放，或删除 `safe` 并重命名 `verifier` 模式。

### 8.3 知识层加固

1. 抽取 `error_family` 常量表为单一真值源（如 `references/error_families.yaml`），文档与 `SCIENTIFIC_ADAPTERS` 共同引用；补一个测试断言"文档族群 ⊆ 实现族群"。
2. 标注 27 个未实现族群的状态，或补齐适配器。
3. 移除 `audit_contract.py:199-209` 对 `thermo[-1].split()` / `last_pe` 字面量的依赖，改为通用模式（如"存在对 split() 结果的位置索引且文件中有 `Step` 表头未被解析"）。

### 8.4 工程加固

1. 补 `tests/__init__.py` + `pyproject.toml`（声明 `requires-python = ">=3.11"` 与 pytest 配置），使 `pytest tests/` 与 `unittest discover` 均可用。
2. 补负面测试：verifier 崩溃、关键词误触发、通过用例（含 job 级 `n_errored_trials>0`）、`stats: null`。
3. 补端到端 CLI 测试，覆盖 `--replay`、`--format`、`--trial` 与多 trial 输出布局。
4. 加 `tests/fixtures/` 真实目录树夹具，替代纯代码构造。
5. 加 `README.md`、`.gitignore`，清理 `.DS_Store`。
6. 删除 `analyze_case.py:20-21` 未使用的 `shutil` / `subprocess` 导入。

---

## 9. 结论

| 维度 | 评价 |
|---|---|
| 架构分层 | **良好** — 五阶段职责清晰，证据/归因分离，可独立测试 |
| 证据规范性 | **良好** — 全链路 `source_file` + `source_pointer` 可回溯，`causal_candidate`/`transient` 区分有价值 |
| 归因正确性 | **不合格** — 2 个 P0（通过用例误报失败、无证据即归因 agent）+ 5 个 P1 |
| 文档-实现一致性 | **不合格** — 6 项核心承诺与实现系统性偏离，知识库 27/37 未接通 |
| 测试充分性 | **偏弱** — 14 个用例全绿但全部位于缺陷盲区，且固化了一处硬规则冲突 |
| 工程完整性 | **偏弱** — 无 README/依赖声明/CI，测试不可标准发现，`--replay safe` 为空壳 |

**核心判断**：该项目的**骨架是对的**——分阶段证据采集、客观/主观分离、结构化编码体系、7 类金标准用例，这些设计在科学计算基准的失败诊断中是有价值且可复用的。问题集中在**归因层**：`analyze_case.py::build_causal_attribution`（628 行、占该文件 75%）以排他决策树替代了文档所承诺的假设竞争，并因此把"没有别的解释"当作"是 agent 的错"。

**建议的修复顺序**：先修 §8.1 的 7 条正确性缺陷并补上对应负面测试（预计可消除本次发现的全部误报），再执行 §8.2 的架构二选一——**这一项必须先决策，否则后续所有改动都会在"脚本定结论还是模型定结论"的二义性上来回摇摆**。知识层（§8.3）与工程层（§8.4）可并行推进，优先级最低。

> 附注：本报告的分析方法与该 Skill 自身的方法论一致——每条结论都给出 `文件:行号` 证据与可复现实验，区分"现象"（如 golden test 全绿）与"根因"（如 Gate 5 缺少正面证据要求），并对无法从代码确定的项（如 7 个 golden case 之外的真实泛化表现）不做断言。
