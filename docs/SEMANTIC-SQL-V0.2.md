# Semantic SQL v0.2 — evidence, structural comparison and bounded gaps

The public grammar remains familiar SQL. A separate v0.2 **investigation compiler**, `tools/semantic_store/semantic_investigation.py`, extends the existing v0.1 bounded graph plan and does **not** reimplement APX algorithms.

## Examples

```sql
SELECT * FROM facts WHERE object_id='root' AND revision='v1'
EXPAND 2 TRACE EVIDENCE;

SELECT * FROM facts WHERE object_id='root' AND revision='v1'
COMPARE WITH 'v2';

SELECT * FROM facts WHERE object_id='root' AND revision='v1'
GOVERNED BY packspec1 FIND GAPS;
```

These clauses run with an **existing authenticated host principal and per-object ACL callback**. There is no network/public console endpoint in this PR. Do not expose the prototype as a service using the development registry's shared token as an object authorization policy.

## Precise behavior and limits

| Clause | What actually runs | What it does NOT establish |
| --- | --- | --- |
| `TRACE EVIDENCE` | Authorized bounded traversal over `WITNESS` edges; up to 5 hops, 100 returned nodes | Witness independence, evidence truth, publisher authority or D15 deception checks |
| `COMPARE WITH 'v2'` | Authorized versions of the same root object, compared by structural payload SHA-256 over visible bounded nodes | Semantic equivalence, RCOC verdict, significance of a changed field |
| `GOVERNED BY ... FIND GAPS` | Requires authorized versioned PackSpec binding and caller-supplied unique finite `required_object_ids` (max 100); reports which IDs were not seen in bounded context | No real-world missing-fact determination, exhaustive corpus search, PackSpec completeness or clause evaluation |

The strict parser accepts exactly one investigation suffix. It rejects write operations, arbitrary SQL, ambiguous combinations and unsupported syntax. Results include explicit `admission: INCONCLUSIVE`, `verification: NOT_PERFORMED`, `can_generate: false`.

For `FIND GAPS`, a read-inaccessible required object is never identified in the output; the check becomes `INCONCLUSIVE_ACCESS_RESTRICTION`. A truncated or 0–5-hop context means `unobserved_ids` are **not discovered in this neighborhood**, not globally absent. The requested PackSpec's fingerprint is returned, but no policy obligation is attested as executed.

## Python host example

```python
from semantic_investigation import compile_investigation, execute_investigation

sql = ("SELECT * FROM facts WHERE object_id='root' AND revision='v1' "
       "GOVERNED BY packspec1 FIND GAPS")
plan = compile_investigation(sql).as_dict()
# Host must bind authenticated principal and object-scoped authorization.
receipt = execute_investigation(
    store, sql, principal=principal, authorize=authorize_object,
    resolve_packspec=resolve_authorized_packspec)
```

The host `resolve_authorized_packspec(principal, ref)` callback must return an approved, authorized version-bound digest and reviewed inventory, e.g.:

```json
{"id":"packspec1","digest":"<64 lowercase SHA-256 hex characters>",
 "authorized":true,"required_object_ids":["root","witness","other"]}
```

This is a **host adapter shape**, not a claim that current Registry API automatically provides required object IDs or an authority proof. Do not infer policy authority from this example.

## Extension strategy

The public syntax is small; typed plan nodes are language-agnostic. Natural-language, spreadsheet and UI adapters can eventually generate the same operations. Before adding real `COLLAPSE FOR`, `RECONSTRUCT ORIGINAL`, `VERIFY PRESERVATION` or `FIND GAPS` over semantic obligations, wire reviewed PackSpec semantics, signed custody, native algorithm parity and independent evaluations. They are **not implemented** here.

## Reproduce

```sh
python -m unittest discover -s tools/semantic_store/tests -p test_semantic_investigation.py -v
python -m unittest discover -s tools/semantic_store/tests -p 'test_*.py' -v
```
