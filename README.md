# RuleStack

**Onchain semantic precedence primitive for resolving overlapping natural-language rules with GenLayer consensus.**

## What RuleStack Does

RuleStack separates two problems that are usually collapsed into one:

```text
Semantic applicability
        ↓
GenLayer consensus

Deterministic precedence
        ↓
RuleStack resolver
```

The LLM is only allowed to classify each candidate rule:

```text
APPLIES
DOES_NOT_APPLY
AMBIGUOUS
```

The LLM never directly returns a policy outcome. It cannot emit:

```text
PERMITTED
DENIED
REQUIRED
CONFLICT
NO_MATCH
UNRESOLVED
```

Those six values are produced by ordinary contract code from consensus-agreed applicability plus numeric authority. The model decides *whether a rule speaks to this action*; the contract decides *what that means*.

## Why It Exists

Natural-language policies overlap. Organizations end up with rules that contradict each other, carve out exceptions, quietly replace older guidance, or are simply unclear about a given case. The reusable primitive RuleStack provides is:

- overlapping natural-language policies that must be reconciled per action;
- different authority levels expressed as a numeric rank rather than prose;
- explicit exceptions that suppress a parent rule;
- supersession, where a newer rule replaces an older one without rewriting history;
- ambiguity, which must block a result only when it could actually change the outcome;
- conflicts, which must surface rather than be silently resolved by a model;
- a deterministic resolution trace explaining every step.

This is not a generic "AI policy checker." The point is not to ask a model whether something is allowed. The point is to let consensus establish applicability and keep precedence logic boring, auditable, and reproducible.

## Model

A rule has an id, text, effect (`PERMIT`, `DENY`, or `REQUIRE`), numeric authority rank, active flag, optional `exception_of` parent, and optional `superseded_by` successor. Higher rank is stronger. Rules are never edited in place: replacing a rule creates a new one and leaves the old text readable.

An applicable exception suppresses its parent only when it is at least as strong as that parent, so a weaker rule cannot gain power by calling itself an exception. Ambiguity blocks the outcome only when it is material — when no clear rule applies, or when an ambiguous rule is at least as strong as the strongest clear rule. A weaker ambiguous rule is recorded in the trace and does not block.

`PERMIT` together with `REQUIRE` yields `REQUIRED`. Any surviving mix that includes `DENY` plus another effect yields `CONFLICT`.

## Architecture

- **Custom leader** — classifies every candidate rule's applicability for one action and context.
- **Independent validator** — re-runs the same classification itself and compares substance, not formatting.
- **Semantic substance validation** — agreement is decided on canonical `(rule_id, status)` pairs. Reasoning prose and key order are ignored.
- **Deterministic resolver** — `_resolve()` applies authority, exception, supersession, and ambiguity rules with no model call at all.
- **Real GenLayer storage** — `TreeMap`, `DynArray`, `Address`, `u32`, and `@allow_storage` dataclasses persist to chain state.
- **Historical immutable evaluations** — evaluations are append-only; re-resolving adds a new row and never mutates the old one.

## Contract

```text
Network: GenLayer Studionet
Chain ID: 61999
Address: 0x13cc20A3f7CC4E0B055Cc85cE8Ea8a4a12846807
Version: 1.0.0
```

Open on GenLayer Studio:

<https://studio.genlayer.com/contracts?import-contract=0x13cc20A3f7CC4E0B055Cc85cE8Ea8a4a12846807>

## Frozen Source

The deployed and certified V1 source is identified by its SHA-256:

```text
ca02cbded0612bb4504c29c8b0b74b802737c9dd76913868d9ff90fc65706c6b
```

Verify the file at any time:

```bash
sha256sum RuleStack.py
```

The contract file is frozen for V1. It is not reformatted, re-sorted, or re-indented, so this hash stays stable and can be checked against the deployed bytecode.

## Public Write Methods

Owner-only except the two public evaluation methods.

| Method | Purpose |
|---|---|
| `add_rule` | Create a rule with text, effect, and authority rank. |
| `add_exception` | Create a rule that is an exception to an existing parent rule. |
| `supersede_rule` | Insert a replacement rule and point the old rule at it. |
| `deactivate_rule` | Deactivate a rule without deleting its text. |
| `evaluate` | Resolve an action and context against the active rule set. Public. |
| `resolve_again` | Re-run resolution over a stored evaluation. Public. |

## Public Read Methods

| Method | Returns |
|---|---|
| `get_contract_info` | Name, version, owner, rule and evaluation counts. |
| `get_rule` | One rule's text, effect, rank, and links. |
| `get_rule_count` | Total rules ever created. |
| `get_rule_ids` | All rule ids in creation order. |
| `get_active_rule_ids` | Ids that are active and not superseded. |
| `get_exceptions_of` | Rules that are exceptions to a given parent. |
| `get_rules_superseding` | Rules that supersede a given rule. |
| `get_evaluation` | One stored evaluation, including its trace. |
| `get_evaluation_count` | Total evaluations stored. |
| `get_evaluation_ids` | Evaluation ids in creation order. |
| `get_decision` | The decision for one evaluation. |
| `get_controlling_rule` | The single controlling rule id, or empty when there are zero or several. |
| `get_controlling_rules` | The full set of controlling rule ids. |
| `get_applicable_rules` | Rules consensus marked `APPLIES`. |
| `get_overridden_rules` | Rules suppressed by an exception. |
| `get_conflicting_rules` | Rules left in conflict after resolution. |
| `get_resolution_trace` | The deterministic step-by-step trace. |

## Testing

Certified V1 totals:

```text
Direct Mode: 65 passed / 0 failed / 0 skipped
Studio:      10 passed / 0 failed
Read Methods: 17/17 PASS
```

Direct Mode runs the contract locally under `genlayer-test` with pickling checks enabled. It needs no Docker:

```bash
pytest tests/direct/test_rulestack.py -q
```

The hosted Studionet certifier is read-only. It inspects the existing deployment through `LATEST_FINAL` state, discovers rule and evaluation ids from the contract itself, and calls all 17 view methods:

```bash
python tests/studio/certify_studionet.py
```

Studionet rate-limits to 30 requests per minute, so the certifier paces its calls and retries. It exits non-zero if any check fails.

The full certification record, including the read-method matrix and lifecycle transactions, is in [CERTIFICATION.md](CERTIFICATION.md).

## Certification Scenario

Evaluation A resolved to `PERMITTED`:

```text
0x0f216ab868d02f77769cdb2a0337e9a0afef3ce6c70dfbc1ac16690b7e8ecb27
```

Evaluation B resolved to `DENIED`:

```text
0xbed5fd0a964ee30a7bb164f3ceb6c1ee7345e26c2292131146bc22a0e1c7a286
```

In both cases the applicability set came from consensus and the controlling rule was chosen by the deterministic resolver, not by the model.

## Repository Layout

```text
RuleStack.py         Frozen V1 contract source (hash-verified, read-only)
README.md            This file
ARCHITECTURE.md      Reviewer-oriented design notes
CERTIFICATION.md     Frozen certification record and evidence
requirements.txt     Test and certification dependencies
tests/
  direct/
    test_rulestack.py      65 Direct Mode behavioural tests
  studio/
    certify_studionet.py   Read-only hosted Studionet certifier
```

## Development

Direct Mode requires Python 3.12 or newer. Install dependencies:

```bash
python3.12 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Run the Direct Mode suite:

```bash
pytest tests/direct/test_rulestack.py -q
# 65 passed
```

Run the read-only Studionet certifier:

```bash
python tests/studio/certify_studionet.py
# READ_METHODS: 17/17 PASS
# STATUS: PASS
```

Verify the frozen source is unmodified:

```bash
sha256sum RuleStack.py
# ca02cbded0612bb4504c29c8b0b74b802737c9dd76913868d9ff90fc65706c6b
```

Deploy to Studionet:

```bash
genlayer network set studionet
genlayer deploy --contract RuleStack.py
```

`RuleStack.py` is frozen. Do not reformat it: any change to whitespace, ordering, or comments changes the hash that identifies the deployed release.