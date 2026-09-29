#!/usr/bin/env python3
"""
Attribution decision table (`tests/test_attribution_decisions.py`)

Drives `run_attribution_engine` directly with hand-built evidence — no filesystem,
no fixture tree — and pins which gate each evidence shape selects, plus the
subcase within Gate 6. This is the payoff of splitting the gates out: the
decision is now a pure function of one dict.

The rows encode the documented Hard Rules, not merely current behavior:

  * rule 3  - `agent_started == false` must yield `infra` (with infra evidence) or
              `unknown` (without), and must NEVER yield `agent`
  * rule 4  - `agent` requires positive evidence; `reward == 0` alone is not enough
  * rule 5  - a verifier hazard needs `failure_binding == "direct"` to blame `verifier`
  * rule 1  - a bare keyword must not become a root cause

It also closes three branches that had no test coverage at all before: rule 3b
(agent never started, no infra evidence), and the validator's FALSE_AGENT_BLAME
and POSITIVE_AGENT_EVIDENCE violation paths.
"""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Any, Dict, List, Tuple

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPT_DIR = REPO_ROOT / "scripts"
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from attribution.engine import GATE_ORDER, run_attribution_engine
from attribution.schema import OUTCOME_KEYS, make_attribution
from discover_artifacts import discover_all
from analyze_case import analyze_single_trial
from tests.archetype_builders import ARCHETYPES
from validate_analysis import validate_all


# ── evidence factories ───────────────────────────────────────────────────────


def _runtime(**kw: Any) -> Dict[str, Any]:
    base = {
        "agent_started": True,
        "verifier_started": True,
        "verification_status": "failed",
        "reward": 0.0,
        "started_at": "2026-01-01T00:00:00Z",
        "finished_at": "2026-01-01T00:10:00Z",
        "execution_status": "completed",
        "exit_status": "completed",
    }
    base.update(kw)
    return base


def _evidence(**kw: Any) -> Dict[str, Any]:
    base = {
        "case_id": "case-1",
        "trial_name": "trial_1",
        "runtime": _runtime(),
        "artifacts": [{"artifact_id": "art:trial_result", "exists": True}],
        "error_observations": [],
        "contract_observations": [],
        "verifier_observations": [],
        "scientific_observations": [],
        "behavioral_signals": [],
        "timeline": [],
    }
    base.update(kw)
    return base


def _fail_log(text: str) -> Dict[str, Any]:
    return {
        "obs_id": "ver:fail_log",
        "type": "verifier_fail_message",
        "matched_text": text,
        "summary": text,
    }


def _infra_error(code: str, **kw: Any) -> Dict[str, Any]:
    base = {
        "error_id": f"err:{code}",
        "code": code,
        "subtype": "container_runtime",
        "stage": "environment_build",
        "matched_text": f"fatal infra: {code}",
        "causal_candidate": True,
    }
    base.update(kw)
    return base


def _sci(family: str, **kw: Any) -> Dict[str, Any]:
    base = {
        "sci_id": f"sci:{family}",
        "software": "quantum-espresso",
        "error_family": family,
        "aliases": [],
        "matched_text": f"{family} reported by solver",
        "source_ref": "trajectory:step:1:tool:0",
        "recovered": False,
        "recovery_event_ref": None,
        "candidate_causes": ["cause_a", "cause_b"],
        "required_discriminating_evidence": ["check_a", "check_b"],
    }
    base.update(kw)
    return base


def _sig(signal_type: str, **kw: Any) -> Dict[str, Any]:
    base = {
        "signal_id": f"sig:{signal_type}",
        "signal_type": signal_type,
        "description": signal_type,
        "event_ref": "trajectory:step:1:tool:0",
    }
    base.update(kw)
    return base


def _contract(alignment: str, **kw: Any) -> Dict[str, Any]:
    base = {
        "contract_id": f"contract:{alignment}",
        "alignment": alignment,
        "item": "Ge.UPF",
        "details": f"contract observation ({alignment})",
    }
    base.update(kw)
    return base


def _agent_event(**kw: Any) -> Dict[str, Any]:
    base = {"event_id": "trajectory:step:9:tool:0", "actor": "agent", "action": "write"}
    base.update(kw)
    return base


# ── decision table ───────────────────────────────────────────────────────────
#
# row = (label, evidence, expected) where expected carries the fields that the
# documented rules actually constrain.

DECISION_TABLE: List[Tuple[str, Dict[str, Any], Dict[str, Any]]] = [
    (
        "gate0 via verification_status",
        _evidence(runtime=_runtime(verification_status="passed")),
        {
            "gate_id": "gate0_passed",
            "category": "none",
            "code": "NONE",
            "verdict": "passed",
            "failure_stage": "none",
        },
    ),
    (
        "gate0 via reward >= 1.0",
        _evidence(runtime=_runtime(verification_status=None, reward=1.0)),
        {
            "gate_id": "gate0_passed",
            "category": "none",
            "code": "NONE",
            "verdict": "passed",
            "failure_stage": "none",
        },
    ),
    (
        "gate1a network failure before agent start (rule 3a)",
        _evidence(
            runtime=_runtime(agent_started=False, verifier_started=False),
            error_observations=[_infra_error("INFRA_EXTERNAL_NETWORK")],
        ),
        {
            "gate_id": "gate1a_infra_prestartup",
            "category": "infra",
            "code": "INFRA_EXTERNAL_NETWORK",
            "verdict": "errored",
            "failure_stage": "environment_build",
        },
    ),
    (
        "gate1a generic container build failure before agent start",
        _evidence(
            runtime=_runtime(agent_started=False, verifier_started=False),
            error_observations=[_infra_error("INFRA_IMAGE_PULL_FAILED")],
        ),
        {
            "gate_id": "gate1a_infra_prestartup",
            "category": "infra",
            "code": "INFRA_IMAGE_PULL_FAILED",
            "verdict": "errored",
        },
    ),
    (
        "gate1b pre-startup with no infra evidence (rule 3b)",
        _evidence(runtime=_runtime(agent_started=False, verifier_started=False)),
        {
            "gate_id": "gate1b_unknown_no_evidence",
            "category": "unknown",
            "code": "UNKNOWN_INSUFFICIENT_EVIDENCE",
            "verdict": "errored",
            "failure_stage": "unknown",
        },
    ),
    (
        "gate2 case contract defect",
        _evidence(
            contract_observations=[_contract("case_defect")],
            verifier_observations=[_fail_log("FAIL: missing asset")],
        ),
        {
            "gate_id": "gate2_case_definition",
            "category": "case",
            "code": "CASE_MISSING_ASSET",
            "verdict": "failed",
            "failure_stage": "agent_execution",
        },
    ),
    (
        "gate3 verifier internal crash (rule 5b)",
        _evidence(
            verifier_observations=[
                {
                    "obs_id": "ver:crash",
                    "type": "verifier_internal_crash",
                    "summary": "FileNotFoundError: /tmp/verify_tmp/refs.json",
                },
                _fail_log("FAIL: verifier crashed"),
            ],
        ),
        {
            "gate_id": "gate3_verifier_defect",
            "category": "verifier",
            "verdict": "failed",
            "failure_stage": "verifier_execution",
        },
    ),
    (
        "gate3 direct-bound parser hazard",
        _evidence(
            verifier_observations=[
                _fail_log("FAIL: could not parse 'VAL= -0.12345D+03'"),
                {
                    "obs_id": "ver:hazard:1",
                    "type": "parser_hazard",
                    "triggered": True,
                    "failure_binding": "direct",
                    "summary": "missing D exponent",
                },
            ],
        ),
        {
            "gate_id": "gate3_verifier_defect",
            "category": "verifier",
            "code": "VERIFIER_REGEX_OR_PARSER_DEFECT",
            "verdict": "failed",
        },
    ),
    (
        "gate3 abstains when a hazard is not causally bound (rule 5)",
        _evidence(
            verifier_observations=[
                _fail_log("FAIL: ENERGY mismatch: got 9.99E+02, expected reference 1.23D+03"),
                {
                    "obs_id": "ver:hazard:1",
                    "type": "parser_hazard",
                    "triggered": False,
                    "failure_binding": "none",
                    "summary": "unrelated D exponent",
                },
            ],
            timeline=[_agent_event()],
        ),
        {"not_gate_id": "gate3_verifier_defect", "not_category": "verifier"},
    ),
    (
        "gate4 structured numerical divergence",
        _evidence(
            verifier_observations=[
                _fail_log(
                    "FAIL: instantaneous_position trajectory_rmsd=0.45 > 0.01 "
                    "(ensemble average matches)"
                ),
            ],
        ),
        {
            "gate_id": "gate4_numerical_divergence",
            "category": "verifier",
            "code": "VERIFIER_TOLERANCE_TOO_STRICT",
            "verdict": "failed",
        },
    ),
    (
        "gate4 abstains on a bare keyword (rule 1)",
        _evidence(verifier_observations=[_fail_log("FAIL: the run looks chaotic")]),
        {"not_gate_id": "gate4_numerical_divergence", "not_category": "verifier"},
    ),
    (
        "gate4 abstains when numerical metrics exist in log but failure check is unrelated",
        _evidence(
            verifier_observations=[
                _fail_log(
                    "INFO: instantaneous_position trajectory_rmsd=0.45 (ensemble average matches)\n"
                    "FAIL: results.json missing key 'energy'"
                )
            ]
        ),
        {
            "not_gate_id": "gate4_numerical_divergence",
            "category": "unknown",
            "code": "UNKNOWN_INSUFFICIENT_EVIDENCE",
        },
    ),
    (
        "gate4 abstains when trajectory diverges but ensemble statistics also fail",
        _evidence(
            verifier_observations=[
                _fail_log(
                    "FAIL: instantaneous_position trajectory_rmsd=0.45 > 0.01 (ensemble average diverged by 50%)"
                )
            ]
        ),
        {
            "not_gate_id": "gate4_numerical_divergence",
            "category": "unknown",
            "code": "UNKNOWN_INSUFFICIENT_EVIDENCE",
        },
    ),
    (
        "gate5 failed with no positive agent evidence (rule 4)",
        _evidence(verifier_observations=[_fail_log("FAIL: agent output absent")]),
        {
            "gate_id": "gate5_insufficient_positive_evidence",
            "category": "unknown",
            "code": "UNKNOWN_INSUFFICIENT_EVIDENCE",
            "verdict": "failed",
            "failure_stage": "unknown",
        },
    ),
    (
        "gate6 subcase 5a unrecovered solver error + repeated action",
        _evidence(
            scientific_observations=[_sci("scf_convergence_not_achieved")],
            behavioral_signals=[_sig("repeated_failed_action")],
            verifier_observations=[_fail_log("FAIL: SCF not converged")],
        ),
        {
            "gate_id": "gate6_agent_primary",
            "subcase_id": "5a",
            "category": "agent",
            "code": "AGENT_ERROR_DIAGNOSIS",
            "failure_stage": "agent_execution",
        },
    ),
    (
        "gate6 subcase 5b missing potential, no dependency search",
        _evidence(
            scientific_observations=[_sci("basis_or_potential_missing")],
            verifier_observations=[_fail_log("FAIL: basis not found")],
        ),
        {
            "gate_id": "gate6_agent_primary",
            "subcase_id": "5b",
            "category": "agent",
            "code": "AGENT_PATH_OR_DEPENDENCY_DISCOVERY",
        },
    ),
    (
        "gate6 subcase 5c continuation mismatch",
        _evidence(
            scientific_observations=[_sci("restart_or_timestep_continuation_mismatch")],
            verifier_observations=[_fail_log("FAIL: continuation diverged")],
        ),
        {
            "gate_id": "gate6_agent_primary",
            "subcase_id": "5c",
            "category": "agent",
            "code": "AGENT_SCIENTIFIC_PARAMETER_SELECTION",
        },
    ),
    (
        "gate6 abstains on isolated other unrecovered solver family (rule 4)",
        _evidence(
            scientific_observations=[_sci("some_other_solver_family")],
            verifier_observations=[_fail_log("FAIL: solver error")],
        ),
        {
            "gate_id": "gate5_insufficient_positive_evidence",
            "category": "unknown",
            "code": "UNKNOWN_INSUFFICIENT_EVIDENCE",
        },
    ),
    (
        "gate6 subcase 5d premature completion",
        _evidence(
            behavioral_signals=[_sig("premature_completion")],
            verifier_observations=[_fail_log("FAIL: required output missing")],
        ),
        {
            "gate_id": "gate6_agent_primary",
            "subcase_id": "5d",
            "category": "agent",
            "code": "AGENT_PREMATURE_TERMINATION",
        },
    ),
    (
        "gate6 subcase 5d agent_mismatch contract",
        _evidence(
            contract_observations=[_contract("agent_mismatch")],
            verifier_observations=[_fail_log("FAIL: schema mismatch")],
        ),
        {
            "gate_id": "gate6_agent_primary",
            "subcase_id": "5d",
            "category": "agent",
            "code": "AGENT_TASK_UNDERSTANDING",
        },
    ),
    (
        "gate6 abstains when agent acted but no causal signals exist (rule 4)",
        _evidence(
            timeline=[_agent_event()],
            verifier_observations=[_fail_log("FAIL: ENERGY mismatch: got 1.0 expected 2.0")],
        ),
        {
            "gate_id": "gate5_insufficient_positive_evidence",
            "category": "unknown",
            "code": "UNKNOWN_INSUFFICIENT_EVIDENCE",
        },
    ),
    (
        "precedence: 5a wins over 5b when both apply",
        _evidence(
            scientific_observations=[_sci("basis_or_potential_missing")],
            behavioral_signals=[_sig("repeated_failed_action")],
            verifier_observations=[_fail_log("FAIL: basis not found")],
        ),
        {"gate_id": "gate6_agent_primary", "subcase_id": "5a", "code": "AGENT_ERROR_DIAGNOSIS"},
    ),
    (
        "precedence: 5b wins over 5c when both families present",
        _evidence(
            scientific_observations=[
                _sci("basis_or_potential_missing", sci_id="sci:basis"),
                _sci("restart_or_timestep_continuation_mismatch", sci_id="sci:restart"),
            ],
            verifier_observations=[_fail_log("FAIL: both")],
        ),
        {
            "gate_id": "gate6_agent_primary",
            "subcase_id": "5b",
            "code": "AGENT_PATH_OR_DEPENDENCY_DISCOVERY",
        },
    ),
]


class TestAttributionDecisionTable(unittest.TestCase):
    def test_decision_table(self) -> None:
        for label, evidence, expected in DECISION_TABLE:
            with self.subTest(row=label):
                analysis = run_attribution_engine(evidence, {"candidate_hypotheses": []})
                trace = analysis["decision_trace"]
                selected = trace["selected"]
                prc = analysis["primary_root_cause"]

                for key in (
                    "gate_id",
                    "subcase_id",
                    "category",
                    "code",
                    "verdict",
                    "failure_stage",
                ):
                    if key in expected:
                        actual = (
                            selected.get(key)
                            if key in ("gate_id", "subcase_id")
                            else (
                                prc.get(key) if key in ("category", "code") else analysis.get(key)
                            )
                        )
                        self.assertEqual(actual, expected[key], f"{label}: {key}")

                # negative assertions: the gate/category must NOT be selected
                if "not_gate_id" in expected:
                    self.assertNotEqual(selected["gate_id"], expected["not_gate_id"], label)
                if "not_category" in expected:
                    self.assertNotEqual(prc["category"], expected["not_category"], label)

    def test_rule_3_forbids_agent_when_agent_never_started(self) -> None:
        """The single most important invariant: never blame an agent that never ran."""
        for label, evidence, _ in DECISION_TABLE:
            if evidence["runtime"].get("agent_started"):
                continue
            with self.subTest(row=label):
                analysis = run_attribution_engine(evidence, {"candidate_hypotheses": []})
                self.assertNotEqual(
                    analysis["primary_root_cause"]["category"],
                    "agent",
                    f"{label}: blamed the agent although agent_started == false",
                )

    def test_output_contract_on_every_row(self) -> None:
        for label, evidence, _ in DECISION_TABLE:
            with self.subTest(row=label):
                analysis = run_attribution_engine(evidence, {"candidate_hypotheses": []})
                expected_keys = list(OUTCOME_KEYS) + ["decision_trace"]
                self.assertEqual(list(analysis.keys()), expected_keys, label)

                trace = analysis["decision_trace"]
                ids = [e["gate_id"] for e in trace["evaluated"]]
                self.assertEqual(
                    ids,
                    list(GATE_ORDER)[: len(ids)],
                    f"{label}: evaluated must be a GATE_ORDER prefix",
                )
                self.assertTrue(
                    trace["evaluated"][-1]["matched"],
                    f"{label}: last evaluated gate must be the match",
                )
                self.assertEqual(trace["selected"]["gate_id"], ids[-1], label)
                self.assertEqual(
                    trace["selected"]["code"], analysis["primary_root_cause"]["code"], label
                )

    def test_trace_is_json_serializable_and_bounded(self) -> None:
        for label, evidence, _ in DECISION_TABLE:
            with self.subTest(row=label):
                analysis = run_attribution_engine(evidence, {"candidate_hypotheses": []})
                text = json.dumps(analysis["decision_trace"])
                self.assertLess(len(text), 4000, f"{label}: trace is unexpectedly large")
                for entry in analysis["decision_trace"]["evaluated"]:
                    for value in entry["checks"].values():
                        self.assertIsInstance(value, (int, float, bool, str, type(None)), label)


class TestAttributionSchemaContract(unittest.TestCase):
    def test_missing_key_is_rejected(self) -> None:
        with self.assertRaises(TypeError):
            make_attribution(**{k: None for k in OUTCOME_KEYS[:-1]})

    def test_extra_key_is_rejected(self) -> None:
        with self.assertRaises(TypeError):
            make_attribution(**{k: None for k in OUTCOME_KEYS}, unexpected_key=1)

    def test_key_order_is_the_contract(self) -> None:
        built = make_attribution(**{k: k for k in OUTCOME_KEYS})
        self.assertEqual(list(built.keys()), list(OUTCOME_KEYS))

    def test_values_are_placed_by_reference(self) -> None:
        """Gates share one list object between `evidence_refs` and hypothesis evidence."""
        shared = ["a"]
        built = make_attribution(**{**{k: None for k in OUTCOME_KEYS}, "evidence_refs": shared})
        self.assertIs(built["evidence_refs"], shared)

    def test_all_gates_emit_the_contract(self) -> None:
        seen = set()
        for _, evidence, _ in DECISION_TABLE:
            analysis = run_attribution_engine(evidence, {"candidate_hypotheses": []})
            seen.add(analysis["decision_trace"]["selected"]["gate_id"])
            self.assertEqual(list(analysis.keys())[:15], list(OUTCOME_KEYS))
            self.assertEqual(analysis["schema_version"], "failure-analysis-v1")
        self.assertEqual(seen, set(GATE_ORDER), "decision table must exercise every gate")


class TestEngineRobustness(unittest.TestCase):
    def test_malformed_signal_entry_does_not_crash_on_a_passing_trial(self) -> None:
        """Hoisted derivations use .get(): a malformed signal must not break gate 0."""
        evidence = _evidence(
            runtime=_runtime(verification_status="passed"),
            behavioral_signals=[{"signal_id": "sig:broken"}],  # no signal_type
            verifier_observations=[{"matched_text": "no obs_id"}],
        )
        analysis = run_attribution_engine(evidence, {"candidate_hypotheses": []})
        self.assertEqual(analysis["verdict"], "passed")

    def test_scientific_recovered_error_is_not_blamed(self) -> None:
        evidence = _evidence(
            scientific_observations=[_sci("scf_convergence_not_achieved", recovered=True)],
            verifier_observations=[_fail_log("FAIL: post-processing condition")],
        )
        analysis = run_attribution_engine(evidence, {"candidate_hypotheses": []})
        self.assertNotEqual(analysis["primary_root_cause"]["category"], "agent")


class TestImportGraph(unittest.TestCase):
    def test_attribution_package_never_imports_analyze_case(self) -> None:
        """The dependency direction is one-way: analyze_case -> attribution."""
        offenders = []
        for path in sorted((SCRIPT_DIR / "attribution").rglob("*.py")):
            text = path.read_text(encoding="utf-8")
            for lineno, line in enumerate(text.splitlines(), start=1):
                stripped = line.strip()
                if stripped.startswith(("import ", "from ")) and "analyze_case" in stripped:
                    offenders.append(f"{path.relative_to(REPO_ROOT)}:{lineno}")
        self.assertEqual(offenders, [], f"attribution modules importing analyze_case: {offenders}")


class TestValidatorHardRuleBranches(unittest.TestCase):
    """
    The validator's rule-violation branches for FALSE_AGENT_BLAME and
    POSITIVE_AGENT_EVIDENCE had no test that actually triggered them: the pipeline
    cannot produce those states, only a hand-authored analysis.json can.
    """

    def _base_pair(self) -> Tuple[Dict[str, Any], Dict[str, Any]]:
        with tempfile.TemporaryDirectory() as tmp:
            job_dir, task_dir = ARCHETYPES["golden7_unknown_missing_logs"](Path(tmp))
            disc = discover_all(job_path=job_dir, task_path=task_dir)
            evidence, analysis, _, _ = analyze_single_trial(disc["trials"][0], job_dir=job_dir)
        return evidence, analysis

    def test_false_agent_blame_branch_fires(self) -> None:
        evidence, analysis = self._base_pair()
        self.assertFalse(evidence["runtime"]["agent_started"])
        analysis["primary_root_cause"]["category"] = "agent"
        analysis["primary_root_cause"]["code"] = "AGENT_ERROR_DIAGNOSIS"
        analysis["evidence_refs"] = ["sig:whatever"]
        ok, errors = validate_all(evidence, analysis, None)
        self.assertFalse(ok)
        self.assertTrue(any("FALSE_AGENT_BLAME" in e for e in errors), errors)

    def test_positive_agent_evidence_branch_fires(self) -> None:
        evidence, analysis = self._base_pair()
        evidence["runtime"]["agent_started"] = True
        analysis["primary_root_cause"]["category"] = "agent"
        analysis["primary_root_cause"]["code"] = "AGENT_RESULT_VALIDATION"
        analysis["evidence_refs"] = ["art:trial_result"]
        analysis["competing_hypotheses"] = [
            {
                "hypothesis_id": "H1",
                "category": "agent",
                "subtype": "result_validation",
                "claim": "x",
                "evidence_for": ["art:trial_result"],
                "evidence_against": [],
                "missing_evidence": [],
                "counterfactual_test": "y",
            },
        ]
        ok, errors = validate_all(evidence, analysis, None)
        self.assertFalse(ok)
        self.assertTrue(any("POSITIVE_AGENT_EVIDENCE" in e for e in errors), errors)

    def test_malformed_decision_trace_is_rejected_but_absence_is_allowed(self) -> None:
        evidence, analysis = self._base_pair()
        analysis.pop("decision_trace", None)
        ok, errors = validate_all(evidence, analysis, None)
        self.assertTrue(ok, f"an analysis without decision_trace must still validate: {errors}")

        analysis["decision_trace"] = {"evaluated": "not-a-list"}
        ok, errors = validate_all(evidence, analysis, None)
        self.assertFalse(ok)
        self.assertTrue(any("decision_trace.evaluated" in e for e in errors), errors)


class TestAgentAttributionTightening(unittest.TestCase):
    """
    Negative tests verifying that tightening the positive agent evidence gate
    prevents false agent blame when causal links are missing.
    """

    def test_isolated_solver_error_without_signals_does_not_blame_agent(self) -> None:
        ev = _evidence(
            scientific_observations=[_sci("generic_linear_solver_divergence")],
            verifier_observations=[_fail_log("FAIL: solver error")],
        )
        an = run_attribution_engine(ev, {"candidate_hypotheses": []})
        self.assertEqual(an["primary_root_cause"]["category"], "unknown")
        self.assertEqual(an["primary_root_cause"]["code"], "UNKNOWN_INSUFFICIENT_EVIDENCE")

    def test_agent_command_with_value_mismatch_without_signal_does_not_blame_agent(self) -> None:
        ev = _evidence(
            timeline=[_agent_event(cmd="python3 run.py")],
            verifier_observations=[_fail_log("FAIL: value mismatch: got 1.0 expected 2.0")],
        )
        an = run_attribution_engine(ev, {"candidate_hypotheses": []})
        self.assertEqual(an["primary_root_cause"]["category"], "unknown")
        self.assertEqual(an["primary_root_cause"]["code"], "UNKNOWN_INSUFFICIENT_EVIDENCE")

    def test_agent_with_unverified_output_and_value_mismatch_attributes_to_agent(self) -> None:
        ev = _evidence(
            behavioral_signals=[
                {
                    "signal_id": "sig:unverified_output",
                    "signal_type": "unverified_output",
                    "description": "Agent wrote results.json without verification",
                    "event_ref": "traj:write_step",
                    "source_pointer": "/steps/0",
                }
            ],
            verifier_observations=[_fail_log("FAIL: value mismatch: got 1.0 expected 2.0")],
        )
        an = run_attribution_engine(ev, {"candidate_hypotheses": []})
        self.assertEqual(an["primary_root_cause"]["category"], "agent")
        self.assertEqual(an["primary_root_cause"]["code"], "AGENT_RESULT_VALIDATION")
        self.assertEqual(an["first_unrecovered_deviation"]["event_ref"], "traj:write_step")

    def test_validator_rejects_generic_agent_timeline_event_as_positive_evidence(self) -> None:
        ev = _evidence(
            timeline=[_agent_event(event_id="traj:step:1", cmd="ls -la")],
            verifier_observations=[_fail_log("FAIL: value mismatch: got 1.0 expected 2.0")],
        )
        an = {
            "schema_version": "failure-analysis-v1",
            "case_id": "test_case",
            "trial_name": "trial_1",
            "verdict": "failed",
            "failure_stage": "agent_execution",
            "detection_stage": "verifier_execution",
            "first_unrecovered_deviation": {
                "status": "identified",
                "event_ref": "traj:step:1",
                "summary": "Agent ran ls",
            },
            "failure_manifestation": {"type": "wrong_value", "summary": "fail"},
            "primary_root_cause": {
                "category": "agent",
                "subtype": "result_validation",
                "code": "AGENT_RESULT_VALIDATION",
                "confidence": 0.5,
                "confidence_kind": "heuristic_evidence_score",
                "evidence_strength": "medium",
                "summary": "Agent produced wrong values",
            },
            "contributing_factors": [],
            "competing_hypotheses": [
                {
                    "hypothesis_id": "H1",
                    "category": "agent",
                    "subtype": "result_validation",
                    "claim": "Agent produced wrong values",
                    "evidence_for": ["traj:step:1"],
                    "evidence_against": [],
                    "missing_evidence": [],
                    "counterfactual_test": "Fix calculation",
                }
            ],
            "evidence_refs": ["traj:step:1"],
            "excluded_hypotheses": [],
            "recommended_actions": [{"owner": "Agent", "action": "Fix calculation"}],
            "skill_prescription": None,
        }
        ok, errors = validate_all(ev, an, None)
        self.assertFalse(ok)
        self.assertTrue(any("POSITIVE_AGENT_EVIDENCE" in e for e in errors), errors)


if __name__ == "__main__":
    unittest.main()
