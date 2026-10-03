# RuleStack V1 architecture

RuleStack resolves overlapping natural-language rules. Semantic applicability and deterministic precedence are separate machines, and the seam between them is the whole design.

## Pipeline

```text
Rule input
    ↓
candidate selection
    ↓
leader semantic classification
    ↓
independent validator classification
    ↓
GenLayer consensus
    ↓
canonical applicability state
    ↓
deterministic precedence resolver
    ↓
persisted evaluation + resolution trace
```

Everything above the seam is non-deterministic and goes through consensus. Everything below it is ordinary code. No model call appears below the seam.

## The boundary

Validators agree only on whether each active, unsuperseded rule `APPLIES`, `DOES_NOT_APPLY`, or is `AMBIGUOUS` for one action and context.

They do not choose the policy result. After consensus, ordinary contract code runs `_resolve()`:

1. Drop inactive and superseded rules before the model ever sees them.
2. Treat ambiguity as material when no clear rule applies, or when an ambiguous rule is at least as strong as the strongest clear rule. Weaker ambiguity is recorded and does not block.
3. Keep the highest `authority_rank`. Rank is numeric. The model is not asked which authority wins.
4. Let an applicable exception suppress its parent only when its rank is greater than or equal to the parent's. A weaker rule cannot gain power by calling itself an exception.
5. Map the surviving effects to exactly one of `PERMITTED`, `DENIED`, `REQUIRED`, `CONFLICT`, `NO_MATCH`, or `UNRESOLVED`.

`PERMIT` together with `REQUIRE` is `REQUIRED`. Any mix that includes `DENY` plus another effect is `CONFLICT`.

## Why the validator reruns classification

A validator that only inspected the leader's output would be checking syntax, not substance. Two designs follow from that mistake. The first accepts anything that parses as JSON, which lets a leader smuggle in statuses it never justified. The second accepts anything whose rule ids and statuses line up structurally, which still delegates the actual judgement to the leader — the validator contributes nothing that was not already decided.

Instead the validator runs the same classification itself, against the same candidate set, and compares. Its vote is only an endorsement of work it independently repeated.

## Why format-only validation is insufficient

The parse step is a gate, not the agreement test. `parse()` rejects malformed responses, duplicate rule ids, unknown statuses, and any id-set mismatch, but a perfectly formed response can still be substantively wrong. Passing the gate means the response is *eligible* for comparison, never that it is *correct*.

Agreement is decided on canonical `(rule_id, status)` pairs in candidate order. Key reordering and extra prose are ignored, because a model that reaches the same statuses with different formatting has not disagreed. A leader error, a missing or duplicate id, an unknown status, or a different status all return `False` — disagreement, which is surfaced rather than absorbed.

## Why authority resolution is deterministic

Authority is a `u32` on the rule record, set by the owner at creation. It is not a semantic judgment and does not require consensus.

If the model were asked which rule wins, two nodes could legitimately read the same rule set differently and produce two different decisions for an identical action — and nothing in the protocol could detect it, because both answers would be well-formed consensus. Moving rank comparison into code makes the outcome a pure function of chain state, so the same inputs always produce the same decision on every node, and the trace can be recomputed and checked.

## Exception handling

An exception is a rule that names a parent through `exception_of`. It suppresses the parent only when it applies *and* is at least as strong as the parent.

The strength requirement is the load-bearing part. Without it, a low-rank rule could attach itself to a high-rank rule and invert the outcome, which is the same class of failure as letting a weak rule outrank a strong one.

## Supersession

Supersession is one-directional and append-only. `supersede_rule` inserts a new rule and points the old rule's `superseded_by` at it. The old text, effect, and rank are never rewritten, so the historical record still explains why an older evaluation reached the answer it did.

A superseding rule must be at least as strong as the rule it replaces, which keeps precedence monotonic over time: a document cannot silently weaken itself by being replaced. Both the exception and supersession graphs reject self-links and any walk that would close a cycle.

## Material ambiguity

Ambiguity blocks only when it could change the result: either nothing applies and something is ambiguous, or an ambiguous rule is at least as strong as the strongest clear rule.

Below that line, ambiguity is recorded in the trace and resolution continues. This matters because the classifier is instructed to return `AMBIGUOUS` whenever a rule's conditions are raised but a required fact is missing, so ambiguity is common. Treating every ambiguous rule as blocking would make the contract unusable on ordinary inputs.

## Controlling rules

Controlling rules are the ones that survive removal and still carry an effect. Usually one. `get_controlling_rule` returns the single id, or an empty string when there are zero or several, so a caller cannot mistake a contested outcome for a clear one; `get_controlling_rules` always returns the full set.

## Historical evaluation immutability

Evaluations are append-only. `resolve_again` does not recompute in place: it stores a new evaluation linked by `parent_evaluation_id` and leaves the previous row untouched.

That preserves the audit property the contract exists to provide. A decision that was published once cannot later be rewritten by a new rule or a changed model, and the trace that justified it remains readable.

## Prompt-injection boundary

Rule text, action, and context are attacker-controlled, because that is what a rule engine consumes. The leader prompt fences each of them inside explicit `<untrusted-...>` delimiters, states that instructions inside those values must never alter behaviour, and names the specific attacks worth blocking: changing statuses, approving a validator, overriding the task, or choosing a final decision.

The prompt is defence in depth, not the primary control. The contract never asks the model for a decision, so an injected instruction that succeeds can at worst produce a wrong applicability status — which the validator independently reproduces, and which the deterministic resolver still cannot turn into an arbitrary outcome.

## Storage

`TreeMap[str, Rule]` and `TreeMap[str, Evaluation]` hold the registries. `DynArray[str]` preserves creation order. Both records are `@allow_storage` dataclasses. Per-rule applicability and the id sets inside an evaluation are deterministic strings so the record stays a flat storage struct; the read methods decode them.

Rules are immutable except for `active` and `superseded_by`. Text, effect, and rank are never rewritten. Exception links are append-only.

The deployer is the owner. Only the owner may add, except, supersede, or deactivate. `evaluate` and `resolve_again` are public.

## Trace

The resolution trace is built by `_resolve()`, not by the model. Status lines follow descending creation sequence, then authority removals, then explicit exceptions, then the controlling set and the decision.

Because it is emitted from code, the trace is deterministic and can be diffed against the on-chain state. It is the artifact a reviewer reads to check that a decision followed from the rule set rather than from model output.