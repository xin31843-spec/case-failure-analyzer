# Failure Taxonomy (`failure-analysis-v1`)

**[English](taxonomy.md) | [简体中文](../zh/taxonomy.md)**

This document defines the standardized classification hierarchy for `case-failure-analyzer`. Every `analysis.json` must assign a `failure_stage`, a `detection_stage`, and a `primary_root_cause` (`category`, `subtype`, `code`).

## 1. Execution & Detection Stages

| Stage ID | Description |
|---|---|
| `environment_build` | Docker image pull, `Dockerfile` build, or `docker compose build` before container start |
| `environment_runtime` | Container startup, volume mounting, or runtime daemon execution |
| `agent_setup` | Installing/initializing the agent binary (`claude-code`, MCP, env vars) inside the container |
| `agent_execution` | Agent reasoning, tool calls, scientific simulation execution, and result generation |
| `verifier_execution` | Execution of `tests/test.sh` and `tests/verify.py` |
| `runner` | Host benchmark runner (`harbor`) orchestration and lifecycle management |

---

## 2. Root Cause Categories & Codes

### 2.1 Infrastructure (`infra`)

Failures caused by container build/runtime, network, LLM API gateway, resource exhaustion, or runner lifecycle.

| Code | Subtype | Description |
|---|---|---|
| `INFRA_CONTAINER_BUILD` | `container_build` | Docker image pull or `Dockerfile` build command failed |
| `INFRA_CONTAINER_RUNTIME` | `container_runtime` | Container crashed, exited unexpectedly, or daemon error |
| `INFRA_EXTERNAL_NETWORK` | `external_network` | `apt`, `pip`, registry pull, or external host unreachable during build/setup |
| `INFRA_API_ERROR` | `api_error` | LLM gateway (`ANTHROPIC_BASE_URL` / proxy) returned HTTP 5xx/4xx or connection reset |
| `INFRA_API_RATE_LIMIT` | `api_rate_limit` | LLM API rate limit (HTTP 429) prevented completion |
| `INFRA_AGENT_TIMEOUT` | `agent_timeout` | Agent execution exceeded wall-clock timeout |
| `INFRA_VERIFIER_TIMEOUT` | `verifier_timeout` | Verifier execution exceeded wall-clock timeout |
| `INFRA_OOM` | `oom` | Out-of-memory kill (`SIGKILL` / exit 137 / `MemoryError`) |
| `INFRA_DISK` | `disk` | Disk space exhaustion (`No space left on device`) |
| `INFRA_PERMISSION` | `permission` | File/mount permission denied caused by container UID/GID setup |
| `INFRA_VOLUME_MOUNT` | `volume_mount` | Missing or broken bind mount for `/workspace` or `/tests` |
| `INFRA_RUNNER_LIFECYCLE` | `runner_lifecycle` | Benchmark harness lock contention, cancellation, or runner crash |

### 2.2 Case Specification (`case`)

Failures caused by incomplete, contradictory, or broken task definitions (`instruction.md`, `environment/assets/`, `task.toml`).

| Code | Subtype | Description |
|---|---|---|
| `CASE_MISSING_ASSET` | `missing_asset` | Prompt references an input, structure, or pseudopotential file absent from the container |
| `CASE_CORRUPT_ASSET` | `corrupt_asset` | Provided input file or asset has unphysical geometry or syntax errors not meant as a debugging task |
| `CASE_AMBIGUOUS_CONTRACT` | `ambiguous_contract` | Prompt leaves critical conventions (units, normalization, column order, directory path) unspecified |
| `CASE_PROMPT_REF_MISMATCH` | `prompt_ref_mismatch` | Reference values in `refs.json` were computed with a different method/parameter than requested in `instruction.md` |
| `CASE_INSUFFICIENT_TIMEOUT` | `insufficient_timeout` | Task requires expensive calculation that cannot finish within `task.toml` timeout on standard CPU resources |

### 2.3 Verifier Defect (`verifier`)

Failures where the agent satisfied the explicit requirements of `instruction.md`, but `tests/verify.py` rejected the output due to a parser bug, hidden contract, or overly tight tolerance.

| Code | Subtype | Description |
|---|---|---|
| `VERIFIER_REGEX_OR_PARSER_DEFECT` | `regex_or_parser_defect` | Verifier regex/parser fails on valid syntax (e.g. Fortran `D+03` exponent, `/` inside namelist strings, multi-line entries) |
| `VERIFIER_HIDDEN_CONTRACT` | `hidden_contract` | Verifier checks for files, namelist keys, or thermo column orders never required by `instruction.md` |
| `VERIFIER_SCHEMA_MISMATCH` | `schema_mismatch` | Verifier checks JSON keys or unit strings that contradict `instruction.md` |
| `VERIFIER_TOLERANCE_TOO_STRICT` | `tolerance_too_strict` | Numerical tolerance is smaller than physical/solver platform noise |
| `VERIFIER_RECOMPUTE_DEFECT` | `recompute_defect` | Verifier's L4 recompute step fails due to verifier's own temporary setup or missing environment paths |

### 2.4 Agent Behavior & Scientific Decisions (`agent`)

Failures where the task, environment, and verifier were sound, and the agent made an unrecovered error.

| Code | Subtype | Description |
|---|---|---|
| `AGENT_TASK_UNDERSTANDING` | `task_understanding` | Agent misunderstood required output filenames, JSON keys, units, or forbidden asset modifications |
| `AGENT_PLANNING` | `planning` | Agent executed steps in an invalid workflow order (e.g. running `bands.x` without matching SCF charge density) |
| `AGENT_TOOL_USE` | `tool_use` | Shell syntax errors, file overwrite mistakes, or broken Python parsing scripts written by the agent |
| `AGENT_PATH_OR_DEPENDENCY_DISCOVERY` | `path_or_dependency_discovery` | Agent failed to locate installed binaries, basis sets, or pseudopotentials that exist in the environment |
| `AGENT_SCIENTIFIC_METHOD_SELECTION` | `scientific_method_selection` | Agent chose an inappropriate physical model, ensemble, functional, or pair style |
| `AGENT_SCIENTIFIC_PARAMETER_SELECTION` | `scientific_parameter_selection` | Agent chose unstable/unconverged parameters (`timestep`, `ecutwfc`, `mixing_beta`, `MAX_SCF`) |
| `AGENT_ERROR_DIAGNOSIS` | `error_diagnosis` | Software emitted a clear diagnostic error, and agent misdiagnosed the physical/input cause |
| `AGENT_RECOVERY` | `recovery` | Agent repeatedly reran a failing command without changing parameters or abandoned recovery prematurely |
| `AGENT_RESULT_VALIDATION` | `result_validation` | Agent miscalculated derived quantities (`results.json` disagrees with raw simulation output) or didn't check sanity |
| `AGENT_PREMATURE_TERMINATION` | `premature_termination` | Agent stopped before completing all required steps or writing `results.json` |

### 2.5 Numerical & Parallel Nondeterminism (`numerical`)

| Code | Subtype | Description |
|---|---|---|
| `NUMERICAL_TRAJECTORY_DIVERGENCE` | `trajectory_divergence` | Chaotic MD divergence across threads/MPI ranks while ensemble averages remain valid |
| `NUMERICAL_SOLVER_NOISE` | `solver_noise` | Minor iterative solver difference across architectures/compilers near threshold boundary |
| `NUMERICAL_UNSEEDED_STOCHASTICITY` | `unseeded_stochasticity` | Thermostat/barostat or conformer generator RNG seed difference |

### 2.6 Unknown (`unknown`)

| Code | Subtype | Description |
|---|---|---|
| `UNKNOWN_INSUFFICIENT_EVIDENCE` | `insufficient_evidence` | Missing logs or competing hypotheses with indistinguishable evidence |
