# RuleStack V1 certification

STATUS: PASS

Re-checked against hosted Studionet on 2026-10-03. Direct Mode was rerun in this workspace. Transaction receipts and `LATEST_FINAL` reads were fetched again from `https://studio.genlayer.com/api`. Nothing below is a planned check.

## Network

| Field | Value |
|---|---|
| Network | Studionet (`studio.genlayer.com`) |
| RPC | `https://studio.genlayer.com/api` |
| Chain ID | 61999 (`0xf22f`) |
| Contract | `0x13cc20A3f7CC4E0B055Cc85cE8Ea8a4a12846807` |
| Deploy tx | `0xaf5e324e79fda4f30ecf6b225a809e898c98beaf805ed3655a3c6292ef7bacd9` |
| Owner | `0x8864f87fd3e16a22b9b2c1350083199f4cbdb043` |
| Source SHA-256 | `ca02cbded0612bb4504c29c8b0b74b802737c9dd76913868d9ff90fc65706c6b` |

Deployed `data.contract_code` (base64) decodes to the same bytes as [RuleStack.py](RuleStack.py) at the repository root. Local hash and deployed hash match.

Deploy receipt: `FINALIZED`, `MAJORITY_AGREE`, leader `execution_result=SUCCESS`, `genvm_result.error_code=null`, `leader_only=false`, 5/5 votes `agree`.

This chain reports successful contract execution as `SUCCESS`, not the literal string `FINISHED_WITH_RETURN`. Success here means `FINALIZED` + `MAJORITY_AGREE` + leader `SUCCESS` + null GenVM error + `leader_only=false`.

Local Docker Studio is not installed in this environment. Certification used hosted Studionet, which is the required network. No `--leader-only` run was used.

## Direct Mode

```text
pytest tests/direct/test_rulestack.py -q
65 passed in 1.86s
failed: 0
skipped: 0
```

`direct_vm.strict_mocks` and `direct_vm.check_pickling` are enabled. The suite covers storage, owner checks, graph and input validation, deterministic resolution, ambiguity, `run_validator` agreement and disagreement, and prompt injection. The validator body compares canonical `(rule_id, status)` and does not `return True`.

## Schema

`get_contract_schema` returns exactly these 23 methods and no others:

Writes: `add_rule`, `add_exception`, `supersede_rule`, `deactivate_rule`, `evaluate`, `resolve_again`

Reads: the 17 frozen view methods listed in the matrix below.

## Lifecycle transactions

Every row was re-read from `eth_getTransactionByHash`. All are `FINALIZED`, `MAJORITY_AGREE`, leader `SUCCESS`, `leader_only=false`, GenVM error null.

| Step | Tx | Notes |
|---|---|---|
| add R1 | `0xbddede1d3879d8de17fe48532c76e03674ace6c602272314f59bf04f47e4942d` | votes 3 agree, 2 idle; one validator execution ERROR |
| add R2 | `0x4bf0393890959f9e6be5bce384d045193682e7b3685fef1836a2c56cc69b2c8c` | majority agree |
| add R3 | `0x574579d61bc6a017e8a7042a8bf4503fa3a468e556b3047a05b5bd6296913677` | majority agree |
| add R4 | `0x4551ae6735dd72c113670e99cac751c3a823670aff2222e65ccdbecb6cfc25ac` | majority agree |
| Evaluation A | `0x0f216ab868d02f77769cdb2a0337e9a0afef3ce6c70dfbc1ac16690b7e8ecb27` | votes 3 agree, 1 idle, 1 disagree |
| Evaluation B | `0xbed5fd0a964ee30a7bb164f3ceb6c1ee7345e26c2292131146bc22a0e1c7a286` | votes 3 agree, 2 disagree; all 4 validator executions SUCCESS |
| add R5 | `0x7962b20cb4360f07be40452afbc204be0c35f383f2f57d8025744cb12847b69f` | relationship fixture only |
| supersede R5 by R6 | `0xe49eff68f6e5f5a46d683da414976467706a07fac53239014d3050b7d6888f80` | |
| deactivate R6 | `0x9200e677113fc139c9f4c4a853ee8de8568f603324710b90303cb74fb9781f4f` | votes 4 agree, 1 idle |

R5/R6 were written after A and B so the relationship reads are real. They are inactive or superseded and are not in the active set, so they do not change A or B.

Some validator processes returned `ERROR`, `idle`, or `disagree`. The leader execution succeeded, majority agreed, and the persisted state matches the leader. That is not leader-only mode.

## Final decisions (LATEST_FINAL)

Evaluation A (`E1`) decision `PERMITTED`. Controlling rule `R2`.

Observed applicability, which came from consensus and was not hardcoded:

```text
R1 APPLIES
R2 APPLIES
R3 DOES_NOT_APPLY
R4 DOES_NOT_APPLY
```

Trace:

```text
R4: DOES_NOT_APPLY
R3: DOES_NOT_APPLY
R2: APPLIES
R1: APPLIES
R2 overrides R1: explicit exception
CONTROLLING: R2
DECISION: PERMITTED
```

R3 is allowed to apply or not. R4 was classified `DOES_NOT_APPLY` rather than the illustrative `APPLIES`. That label does not change the result: R2 at rank 300 is the applicable exception to R1, and a rank-100 permit would be removed if it had applied. The required deterministic outcome holds.

Evaluation B (`E2`) decision `DENIED`. Controlling rule `R1`.

```text
R4: APPLIES
R3: AMBIGUOUS
R2: DOES_NOT_APPLY
R1: APPLIES
R4 removed: lower authority
R3 ambiguity recorded: lower precedence cannot change result
CONTROLLING: R1
DECISION: DENIED
```

R2 does not apply. R1 controls. R3's ambiguity is below R1's rank, so it is recorded and does not block.

`resolve_again` is on the deployed schema and is covered by Direct Mode. The canonical A/B scenario does not call it.

## Read-method matrix

Snapshot: `LATEST_FINAL` after the lifecycle above. All 17 methods returned without revert. Parameterized methods were called with the arguments shown. Re-fetched on 2026-10-03: contract info, rule count, active ids, exceptions of R1, rules superseding R5, both decisions, both controlling rules, both traces. The remaining rows are the certification script's final-state calls against the same address; they agree with that snapshot (`rule_count=6`, `evaluation_count=2`, active `R1–R4`).

| Method | Args | Expected property | Actual | Result |
|---|---|---|---|---|
| get_contract_info | — | name RuleStack, version 1.0.0, owner set, counts | name RuleStack, version 1.0.0, owner `0x8864…b043`, rules 6, evaluations 2 | PASS |
| get_rule | R1 | DENY, rank 300, active, no parent | text and effect match; sequence 1; exception_of empty | PASS |
| get_rule_count | — | 6 | 6 | PASS |
| get_rule_ids | — | creation order includes R1–R6 | `["R1","R2","R3","R4","R5","R6"]` | PASS |
| get_active_rule_ids | — | R1–R4 only | `["R1","R2","R3","R4"]` | PASS |
| get_exceptions_of | R1 | R2 | `["R2"]` | PASS |
| get_rules_superseding | R5 | R6 | `["R6"]`; R1 returns `[]` | PASS |
| get_evaluation | E1 | immutable action/context and PERMITTED | E1 stored as written; parent empty; decision PERMITTED | PASS |
| get_evaluation_count | — | 2 | 2 | PASS |
| get_evaluation_ids | — | E1 then E2 | `["E1","E2"]` | PASS |
| get_decision | E1 / E2 | PERMITTED / DENIED | PERMITTED / DENIED | PASS |
| get_controlling_rule | E1 / E2 | single id | R2 / R1 | PASS |
| get_controlling_rules | E1 / E2 | full set | `["R2"]` / `["R1"]` | PASS |
| get_applicable_rules | E1 / E2 | consensus APPLIES set | `["R1","R2"]` / `["R1","R4"]` | PASS |
| get_overridden_rules | E1 / E2 | exception suppression | `["R1"]` / `[]` | PASS |
| get_conflicting_rules | E1 / E2 | none in this scenario | `[]` / `[]` | PASS |
| get_resolution_trace | E1 / E2 | deterministic trace, not model prose | traces quoted above | PASS |

`get_rule(R2)`: PERMIT, rank 300, `exception_of=R1`. `get_rule(R5)`: still readable, `superseded_by=R6`, not in the active set. `get_exceptions_of(R3)` is `[]`. `get_rules_superseding(R1)` is `[]`. `get_evaluation(E2)` stores the second context and decision DENIED.

## Gates

| Gate | Result |
|---|---|
| custom leader | PASS |
| independent validator | PASS |
| substance validation (id + status, not JSON shape) | PASS |
| validator disagreement test | PASS |
| real GenLayer storage | PASS |
| pickling | PASS |
| owner permissions | PASS |
| cycle guards | PASS |
| input guards | PASS |
| prompt injection | PASS |
| Read methods | 17/17 PASS |

OPEN_CRITICAL: none

OPEN_HIGH: none

## Release-time reproduction

This section is distinct from the historical certification above. The
historical record is the original Studio write run, including the lifecycle
transactions. The checks below were re-executed from this repository before the
public GitHub release, and neither re-runs nor mutates certified on-chain state.

```text
Reproduced before GitHub release:
Direct tests: 65/65 PASS
Hosted Studionet read verification: 17/17 PASS
Frozen source hash: MATCH
```

Kept separate on purpose:

```text
Historical certification:
  10 Studio tests PASS (original write run, lifecycle transactions above)

Release-time reproduction:
  65 Direct tests PASS
  17/17 deployed final-state reads PASS
```

What was actually re-executed:

| Check | Command | Result |
|---|---|---|
| Direct Mode suite | `pytest tests/direct/test_rulestack.py -q` | 65 passed, 0 failed, 0 skipped |
| Hosted read verification | `python tests/studio/certify_studionet.py` | `READ_METHODS: 17/17 PASS`, `STATUS: PASS`, exit 0 |
| Frozen source | `sha256sum RuleStack.py` | `ca02cbde…c6b`, unchanged |

`tests/studio/certify_studionet.py` is strictly read-only. It reads
`LATEST_FINAL` state through `TransactionHashVariant.LATEST_FINAL`, discovers
rule ids via `get_rule_ids()` and evaluation ids via `get_evaluation_ids()`
rather than assuming `R1`–`R6` or `E1`/`E2`, and calls all 17 view methods. It
does not redeploy the contract and does not create new evaluations.

It discovered `PERMITTED` evaluation `E1` and `DENIED` evaluation `E2` from
deployed state, matching the lifecycle recorded above. It also cross-checks
that `get_decision` agrees with `get_evaluation`, that `get_controlling_rule`
returns the single id or empty when there are zero or several, that overridden
rules are never also controlling, and that each trace contains the
`CONTROLLING:` and `DECISION:` lines matching its structured decision.

The historical "10 Studio tests" figure above was **not** re-executed here.
That was a write run; re-running it would create new evaluations and mutate
certified state. Only the read verification was reproduced.
