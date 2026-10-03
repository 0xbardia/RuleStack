#!/usr/bin/env python3
"""Read-only certification of the deployed RuleStack V1 contract on Studionet.

This script never writes. It inspects the existing frozen deployment through
`LATEST_FINAL` state only, discovers rule and evaluation ids from the contract
itself, calls all 17 public view methods, and checks that the returned
structures are internally coherent.

It does NOT redeploy the contract and does NOT create evaluations. The
historical Studio write certification is recorded separately in
CERTIFICATION.md; this script is a read verification, not a re-execution of it.

Usage:
    python tests/studio/certify_studionet.py

Exit code is non-zero if any check fails.
"""

import json
import sys
import time

from eth_account import Account

from genlayer_py import create_client
from genlayer_py.chains import studionet
from genlayer_py.types import TransactionHashVariant

CONTRACT_ADDRESS = "0x13cc20A3f7CC4E0B055Cc85cE8Ea8a4a12846807"
EXPECTED_CHAIN_ID = 61999
EXPECTED_NAME = "RuleStack"
EXPECTED_VERSION = "1.0.0"

STATE = TransactionHashVariant.LATEST_FINAL

READ_METHODS = [
    "get_contract_info",
    "get_rule",
    "get_rule_count",
    "get_rule_ids",
    "get_active_rule_ids",
    "get_exceptions_of",
    "get_rules_superseding",
    "get_evaluation",
    "get_evaluation_count",
    "get_evaluation_ids",
    "get_decision",
    "get_controlling_rule",
    "get_controlling_rules",
    "get_applicable_rules",
    "get_overridden_rules",
    "get_conflicting_rules",
    "get_resolution_trace",
]

failures = []
matrix = []


MIN_SECONDS_BETWEEN_CALLS = 2.5
_last_call = 0.0


def read(client, method, *args):
    """Read one view method from LATEST_FINAL state.

    Studionet rate-limits to 30 requests per minute, so calls are spaced out
    and rate-limit errors are retried with backoff.
    """
    global _last_call
    for attempt in range(6):
        elapsed = time.monotonic() - _last_call
        if elapsed < MIN_SECONDS_BETWEEN_CALLS:
            time.sleep(MIN_SECONDS_BETWEEN_CALLS - elapsed)
        _last_call = time.monotonic()
        try:
            return client.read_contract(
                address=CONTRACT_ADDRESS,
                function_name=method,
                args=list(args) if args else None,
                transaction_hash_variant=STATE,
            )
        except Exception as exc:  # noqa: BLE001
            message = str(exc)
            if "Rate limit" in message or "rate limit" in message:
                wait = MIN_SECONDS_BETWEEN_CALLS * (attempt + 3)
                print(f"  rate limited on {method}, retrying in {wait:.0f}s")
                time.sleep(wait)
                continue
            raise


def record(method, ok, detail=""):
    matrix.append((method, ok, detail))
    if not ok:
        failures.append(f"{method}: {detail}")
    return ok


def as_json(value):
    """Contract views return JSON strings."""
    if isinstance(value, (dict, list)):
        return value
    return json.loads(value)


def main():
    print("RULESTACK STUDIONET READ CERTIFICATION")
    print()

    # 1. RPC reachable / chain id.
    try:
        # An ephemeral, unfunded account is generated at runtime for read
        # signing. No key material is stored in this repository.
        account = Account.create()
        client = create_client(chain=studionet, account=account)
        chain_id = client.chain.id
    except Exception as exc:  # noqa: BLE001
        print(f"RPC: FAIL ({exc})")
        print()
        print("STATUS: FAIL")
        return 1

    print("NETWORK: Studionet")
    print(f"CHAIN_ID: {chain_id}")
    print(f"CONTRACT: {CONTRACT_ADDRESS}")
    print(f"STATE: {STATE.value}")
    print()
    if chain_id != EXPECTED_CHAIN_ID:
        print(f"CHAIN_ID_MISMATCH: expected {EXPECTED_CHAIN_ID}")
        print()
        print("STATUS: FAIL")
        return 1

    # 2. Contract identity.
    try:
        info = as_json(read(client, "get_contract_info"))
    except Exception as exc:  # noqa: BLE001
        print(f"get_contract_info: FAIL ({exc})")
        print()
        print("READ_METHODS: 0/17 PASS")
        print("STATUS: FAIL")
        return 1

    if info.get("name") != EXPECTED_NAME:
        failures.append(f"name is {info.get('name')!r}, expected {EXPECTED_NAME!r}")
    if info.get("version") != EXPECTED_VERSION:
        failures.append(
            f"version is {info.get('version')!r}, expected {EXPECTED_VERSION!r}"
        )
    record("get_contract_info", True)

    # 3. Discover ids from deployed state (never hardcoded).
    try:
        rule_ids = as_json(read(client, "get_rule_ids"))
        evaluation_ids = as_json(read(client, "get_evaluation_ids"))
        rule_count = read(client, "get_rule_count")
        evaluation_count = read(client, "get_evaluation_count")
        active_ids = as_json(read(client, "get_active_rule_ids"))
    except Exception as exc:  # noqa: BLE001
        failures.append(f"id discovery failed: {exc}")
        rule_ids, evaluation_ids, active_ids = [], [], []

    if not rule_ids:
        failures.append("no rule ids discovered")
    if not evaluation_ids:
        failures.append("no evaluation ids discovered")

    # Internal coherence of the registries.
    if str(rule_count) != str(len(rule_ids)):
        failures.append(f"get_rule_count={rule_count} but {len(rule_ids)} ids")
    if str(evaluation_count) != str(len(evaluation_ids)):
        failures.append(
            f"get_evaluation_count={evaluation_count} but "
            f"{len(evaluation_ids)} ids"
        )
    if str(info.get("rule_count")) != str(len(rule_ids)):
        failures.append("contract_info rule_count disagrees with get_rule_ids")
    if str(info.get("evaluation_count")) != str(len(evaluation_ids)):
        failures.append("contract_info evaluation_count disagrees with get_evaluation_ids")
    for rid in active_ids:
        if rid not in rule_ids:
            failures.append(f"active id {rid} is not in get_rule_ids")

    record("get_rule_count", True)
    record("get_rule_ids", True)
    record("get_active_rule_ids", True)
    record("get_evaluation_count", True)
    record("get_evaluation_ids", True)

    # 4. Rule-parameterized views, using real ids from state.
    probe_rule = rule_ids[0] if rule_ids else None
    if probe_rule is None:
        for method in ("get_rule", "get_exceptions_of", "get_rules_superseding"):
            record(method, False, "no rule id available")
    else:
        try:
            rule = as_json(read(client, "get_rule", probe_rule))
            if rule.get("rule_id") != probe_rule:
                failures.append(
                    f"get_rule returned {rule.get('rule_id')!r} for {probe_rule!r}"
                )
            if rule.get("effect") not in ("PERMIT", "DENY", "REQUIRE"):
                failures.append(f"unexpected effect {rule.get('effect')!r}")
            if not isinstance(rule.get("authority_rank"), int):
                failures.append("authority_rank is not an int")
            record("get_rule", True)

            exceptions = as_json(read(client, "get_exceptions_of", probe_rule))
            for child in exceptions:
                child_rule = as_json(read(client, "get_rule", child))
                if child_rule.get("exception_of") != probe_rule:
                    failures.append(
                        f"get_exceptions_of({probe_rule}) returned {child} "
                        f"whose exception_of is "
                        f"{child_rule.get('exception_of')!r}"
                    )
            record("get_exceptions_of", True)

            superseding = as_json(
                read(client, "get_rules_superseding", probe_rule)
            )
            for successor in superseding:
                if as_json(read(client, "get_rule", probe_rule)).get(
                    "superseded_by"
                ) != successor:
                    failures.append(
                        f"get_rules_superseding({probe_rule}) returned "
                        f"{successor}, which is not its superseded_by"
                    )
            record("get_rules_superseding", True)
        except Exception as exc:  # noqa: BLE001
            for method in ("get_rule", "get_exceptions_of", "get_rules_superseding"):
                if not any(m[0] == method for m in matrix):
                    record(method, False, str(exc))

    # 5. Evaluation-parameterized views, using real ids from state.
    permitted_id = None
    denied_id = None
    decisions = {}

    if not evaluation_ids:
        for method in (
            "get_evaluation",
            "get_decision",
            "get_controlling_rule",
            "get_controlling_rules",
            "get_applicable_rules",
            "get_overridden_rules",
            "get_conflicting_rules",
            "get_resolution_trace",
        ):
            record(method, False, "no evaluation id available")
    else:
        for evaluation_id in evaluation_ids:
            try:
                evaluation = as_json(read(client, "get_evaluation", evaluation_id))
                if evaluation.get("evaluation_id") != evaluation_id:
                    failures.append(
                        f"get_evaluation({evaluation_id}) returned "
                        f"{evaluation.get('evaluation_id')!r}"
                    )
                decision = read(client, "get_decision", evaluation_id)
                decisions[evaluation_id] = decision
                if decision != evaluation.get("decision"):
                    failures.append(
                        f"get_decision({evaluation_id})={decision!r} disagrees with "
                        f"get_evaluation decision={evaluation.get('decision')!r}"
                    )
                if decision not in (
                    "PERMITTED",
                    "DENIED",
                    "REQUIRED",
                    "CONFLICT",
                    "NO_MATCH",
                    "UNRESOLVED",
                ):
                    failures.append(f"{evaluation_id} has unknown decision {decision!r}")
                if decision == "PERMITTED":
                    permitted_id = evaluation_id
                if decision == "DENIED":
                    denied_id = evaluation_id
            except Exception as exc:  # noqa: BLE001
                failures.append(f"evaluation {evaluation_id}: {exc}")
        record("get_evaluation", not any("get_evaluation" in f for f in failures))
        record("get_decision", not any("get_decision" in f for f in failures))

        for evaluation_id in evaluation_ids:
            try:
                payload = as_json(read(client, "get_evaluation", evaluation_id))
                controlling = as_json(
                    read(client, "get_controlling_rules", evaluation_id)
                )
                single = read(client, "get_controlling_rule", evaluation_id)
                applicable = as_json(
                    read(client, "get_applicable_rules", evaluation_id)
                )
                overridden = as_json(
                    read(client, "get_overridden_rules", evaluation_id)
                )
                conflicting = as_json(
                    read(client, "get_conflicting_rules", evaluation_id)
                )
                trace = read(client, "get_resolution_trace", evaluation_id)

                if controlling != payload.get("controlling_rules"):
                    failures.append(
                        f"get_controlling_rules({evaluation_id}) disagrees with "
                        f"get_evaluation"
                    )
                if applicable != payload.get("applicable_rules"):
                    failures.append(
                        f"get_applicable_rules({evaluation_id}) disagrees with "
                        f"get_evaluation"
                    )
                if overridden != payload.get("overridden_rules"):
                    failures.append(
                        f"get_overridden_rules({evaluation_id}) disagrees with "
                        f"get_evaluation"
                    )
                if conflicting != payload.get("conflicting_rules"):
                    failures.append(
                        f"get_conflicting_rules({evaluation_id}) disagrees with "
                        f"get_evaluation"
                    )
                # get_controlling_rule is the single id, or empty when 0 or >1.
                expected_single = (
                    controlling[0] if len(controlling) == 1 else ""
                )
                if single != expected_single:
                    failures.append(
                        f"get_controlling_rule({evaluation_id})={single!r}, "
                        f"expected {expected_single!r}"
                    )
                # The trace must agree with the structured decision.
                decision = decisions.get(evaluation_id)
                if f"DECISION: {decision}" not in trace:
                    failures.append(
                        f"trace for {evaluation_id} does not contain "
                        f"'DECISION: {decision}'"
                    )
                if "CONTROLLING:" not in trace:
                    failures.append(
                        f"trace for {evaluation_id} has no CONTROLLING line"
                    )
                # Overridden rules are removed from the controlling set.
                for rid in overridden:
                    if rid in controlling:
                        failures.append(
                            f"{evaluation_id}: {rid} is both overridden and "
                            f"controlling"
                        )
            except Exception as exc:  # noqa: BLE001
                failures.append(f"{evaluation_id} views: {exc}")

        for method in (
            "get_controlling_rule",
            "get_controlling_rules",
            "get_applicable_rules",
            "get_overridden_rules",
            "get_conflicting_rules",
            "get_resolution_trace",
        ):
            record(method, not any(method in f for f in failures))

    # 6. Required scenario coverage.
    if not permitted_id:
        failures.append("no stored evaluation is PERMITTED")
    if not denied_id:
        failures.append("no stored evaluation is DENIED")

    # Report.
    print()
    for method, ok, detail in matrix:
        print(f"{method}: {'PASS' if ok else 'FAIL'}{f' ({detail})' if detail else ''}")

    passed = sum(1 for _, ok, _ in matrix if ok)
    print()
    print(f"READ_METHODS: {passed}/17 PASS")
    print(f"PERMITTED_EVALUATION: {permitted_id or 'NONE'}")
    print(f"DENIED_EVALUATION: {denied_id or 'NONE'}")
    print()

    if failures:
        print("FAILURES:")
        for failure in failures:
            print(f"  - {failure}")
        print()

    status = "PASS" if passed == 17 and not failures else "FAIL"
    print(f"STATUS: {status}")
    return 0 if status == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())