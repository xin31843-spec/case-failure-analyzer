# 失败分类学规范 (`failure-analysis-v1`)

**[English](../en/taxonomy.md) | [简体中文](taxonomy.md)**

本文档定义了 `case-failure-analyzer` 的标准化根因分类体系。每份 `analysis.json` 都必须指定发生阶段 (`failure_stage`)、暴露/检测阶段 (`detection_stage`) 以及唯一主根因 (`primary_root_cause`：`category`、`subtype`、`code`)。

## 1. 执行与检测阶段 (`Execution & Detection Stages`)

| 阶段 ID (`Stage ID`) | 说明 |
|---|---|
| `environment_build` | 容器启动前的 Docker 镜像拉取、`Dockerfile` 构建或 `docker compose build` 阶段 |
| `environment_runtime` | 容器启动、卷挂载或运行时守护进程执行阶段 |
| `agent_setup` | 容器内安装/初始化 Agent 二进制文件（如 `claude-code`、MCP、环境变量）阶段 |
| `agent_execution` | Agent 推理、工具调用、科学计算模拟执行及结果产物生成阶段 |
| `verifier_execution` | 执行 `tests/test.sh` 与 `tests/verify.py` 评测校验阶段 |
| `runner` | 宿主机评测调度器（如 `harbor`）编排与生命周期管理阶段 |

---

## 2. 根因大类与编码 (`Root Cause Categories & Codes`)

### 2.1 基础设施故障 (`infra`)

由容器构建/运行、外部网络、LLM API 网关、系统资源耗尽或调度器生命周期引起的失败。

| 编码 (`Code`) | 子类 (`Subtype`) | 说明 |
|---|---|---|
| `INFRA_CONTAINER_BUILD` | `container_build` | Docker 镜像拉取或 `Dockerfile` 构建命令失败 |
| `INFRA_CONTAINER_RUNTIME` | `container_runtime` | 容器崩溃、异常退出或 Docker 守护进程报错 |
| `INFRA_EXTERNAL_NETWORK` | `external_network` | 构建或初始化期间 `apt`、`pip`、镜像仓库拉取或外部主机无法访问 |
| `INFRA_API_ERROR` | `api_error` | LLM 网关（`ANTHROPIC_BASE_URL` / 代理）返回 HTTP 5xx/4xx 或连接重置 |
| `INFRA_API_RATE_LIMIT` | `api_rate_limit` | LLM API 触发限流（HTTP 429）导致任务中断 |
| `INFRA_AGENT_TIMEOUT` | `agent_timeout` | Agent 执行超出挂钟超时上限 |
| `INFRA_VERIFIER_TIMEOUT` | `verifier_timeout` | Verifier 评测脚本执行超出挂钟超时上限 |
| `INFRA_OOM` | `oom` | 内存耗尽被系统终止（`SIGKILL` / 退出码 137 / `MemoryError`） |
| `INFRA_DISK` | `disk` | 磁盘空间耗尽（`No space left on device`） |
| `INFRA_PERMISSION` | `permission` | 容器 UID/GID 设置导致的文件或挂载目录权限拒绝 |
| `INFRA_VOLUME_MOUNT` | `volume_mount` | `/workspace` 或 `/tests` 绑定挂载缺失或损坏 |
| `INFRA_RUNNER_LIFECYCLE` | `runner_lifecycle` | 评测框架锁竞争、任务被取消或 Runner 进程崩溃 |

### 2.2 题目与任务定义缺陷 (`case`)

由不完整、自相矛盾或损坏的任务定义（`instruction.md`、`environment/assets/`、`task.toml`）引起的失败。

| 编码 (`Code`) | 子类 (`Subtype`) | 说明 |
|---|---|---|
| `CASE_MISSING_ASSET` | `missing_asset` | Prompt 引用了容器内根本不存在的输入文件、结构文件或赝势文件 |
| `CASE_CORRUPT_ASSET` | `corrupt_asset` | 题目提供的输入或资产文件存在非物理几何构型或非预期语法错误（且并非排错类赛题） |
| `CASE_AMBIGUOUS_CONTRACT` | `ambiguous_contract` | Prompt 未明确关键约定（如单位制、归一化方式、列顺序、输出目录路径） |
| `CASE_PROMPT_REF_MISMATCH` | `prompt_ref_mismatch` | `refs.json` 中的参考值所用的计算方法/参数与 `instruction.md` 要求不一致 |
| `CASE_INSUFFICIENT_TIMEOUT` | `insufficient_timeout` | 任务所需的计算量在标准 CPU 资源下无法在 `task.toml` 规定的时限内完成 |

### 2.3 评测器缺陷 (`verifier`)

Agent 满足了 `instruction.md` 的显式要求，但 `tests/verify.py` 因解析器缺陷、隐式契约或过严容差而拒绝了结果。

| 编码 (`Code`) | 子类 (`Subtype`) | 说明 |
|---|---|---|
| `VERIFIER_REGEX_OR_PARSER_DEFECT` | `regex_or_parser_defect` | Verifier 正则/解析器在合法语法上解析失败（如 Fortran `D+03` 科学计数法、namelist 字符串内的 `/`、多行条目） |
| `VERIFIER_HIDDEN_CONTRACT` | `hidden_contract` | Verifier 检查了 `instruction.md` 从未要求的文件、namelist 键或热力学输出列顺序 |
| `VERIFIER_SCHEMA_MISMATCH` | `schema_mismatch` | Verifier 检查的 JSON 键名或单位字符串与 `instruction.md` 相矛盾 |
| `VERIFIER_TOLERANCE_TOO_STRICT` | `tolerance_too_strict` | 数值容差小于物理求解器或跨平台浮点噪声下界 |
| `VERIFIER_RECOMPUTE_DEFECT` | `recompute_defect` | Verifier 自身的重算（L4 recompute）步骤因其临时目录或参考文件路径缺失而崩溃 |

### 2.4 Agent 行为与科学决策失误 (`agent`)

题目定义、运行环境与评测器均正常，Agent 在执行过程中出现了未恢复的错误决策或操作。

| 编码 (`Code`) | 子类 (`Subtype`) | 说明 |
|---|---|---|
| `AGENT_TASK_UNDERSTANDING` | `task_understanding` | Agent 误解了要求的输出文件名、JSON 键名、物理单位或禁止修改资产文件的规定 |
| `AGENT_PLANNING` | `planning` | Agent 按错误的工作流顺序执行步骤（例如未生成匹配的 SCF 电荷密度就直接运行 `bands.x`） |
| `AGENT_TOOL_USE` | `tool_use` | Agent 编写的 Shell 命令存在语法错误、错误覆盖文件或编写了有缺陷的 Python 提取脚本 |
| `AGENT_PATH_OR_DEPENDENCY_DISCOVERY` | `path_or_dependency_discovery` | Agent 未能在环境中搜索并定位已安装的可执行程序、基组或赝势库目录 |
| `AGENT_SCIENTIFIC_METHOD_SELECTION` | `scientific_method_selection` | Agent 选择了不恰当的物理模型、系综、泛函或势函数类型 |
| `AGENT_SCIENTIFIC_PARAMETER_SELECTION` | `scientific_parameter_selection` | Agent 选择了不稳定或无法收敛的计算参数（如 `timestep`、`ecutwfc`、`mixing_beta`、`MAX_SCF`） |
| `AGENT_ERROR_DIAGNOSIS` | `error_diagnosis` | 科学计算软件已输出明确的诊断报错，但 Agent 误判了物理或输入层面的原因 |
| `AGENT_RECOVERY` | `recovery` | Agent 在未修改关键参数的情况下重复执行失败命令，或过早放弃恢复 |
| `AGENT_RESULT_VALIDATION` | `result_validation` | Agent 后处理计算派生量出错（`results.json` 与原始模拟输出不符）或未做合理性自检 |
| `AGENT_PREMATURE_TERMINATION` | `premature_termination` | Agent 在完成全部必要计算步骤或写出 `results.json` 前提前结束任务 |

### 2.5 数值与并行非确定性 (`numerical`)

| 编码 (`Code`) | 子类 (`Subtype`) | 说明 |
|---|---|---|
| `NUMERICAL_TRAJECTORY_DIVERGENCE` | `trajectory_divergence` | 分子动力学（MD）在不同线程/MPI 进程数下出现混沌瞬时轨迹发散，但系综统计均值与守恒量保持一致 |
| `NUMERICAL_SOLVER_NOISE` | `solver_noise` | 不同硬件架构或编译器下迭代求解器在判据阈值边界附近的微小浮点差异 |
| `NUMERICAL_UNSEEDED_STOCHASTICITY` | `unseeded_stochasticity` | 控温器/控压器或构象生成器未固定随机数种子引起的随机差异 |

### 2.6 证据不足 / 未知 (`unknown`)

| 编码 (`Code`) | 子类 (`Subtype`) | 说明 |
|---|---|---|
| `UNKNOWN_INSUFFICIENT_EVIDENCE` | `insufficient_evidence` | 关键日志缺失，或现有客观证据无法区分多个竞争假设 |
