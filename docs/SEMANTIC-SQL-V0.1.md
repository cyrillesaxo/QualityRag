# Semantic SQL v0.1 — familiar surface, strict internal plan

This is a **bounded research query language**, not a general SQL engine and not a new requirement for users. The purpose is to reuse familiar `SELECT / FROM / WHERE / LIMIT` syntax while compiling into the existing authorized Semantic Store graph retrieval API. It preserves source and governance context and never grants admission.

## First executable grammar

```sql
SELECT * FROM facts
WHERE object_id = 'root'
  AND revision = 'r1'
LIMIT 20;
```

Optionally select one graph layer:

```sql
SELECT * FROM facts
WHERE object_id = 'root'
  AND revision = 'r1'
  AND layer = 'WITNESS'
LIMIT 10;
```

`facts` is a **virtual view of the neighborhood of a known semantic object**, not a table scan. v0.1 requires one explicit root ID and revision. No joins, aggregation, recursion, arbitrary SQL, write operations, pattern matching or semantic extraction are accepted. An omitted layer means KnowledgeGraph and WitnessGraph. REGIME is supported explicitly.

## API and execution

```python
# Run with tools/semantic_store on PYTHONPATH, in an authorized local host.
from semantic_sql import compile_sql, execute_sql
plan = compile_sql("SELECT * FROM facts WHERE object_id='root' AND revision='r1' LIMIT 20")
print(plan.as_dict())
result = execute_sql(store, "SELECT * FROM facts WHERE object_id='root' AND revision='r1'",
                     principal=authenticated_principal,
                     authorize=per_object_authorization_callback)
```

`execute_sql` never interpolates supplied strings into SQL. It calls `query_context`, which performs bounded, parameterized retrieval and checks every visited object through the caller-provided policy. Do **not** pass an always-true authorizer from a network endpoint.

Every result explicitly returns `admission: INCONCLUSIVE`, `can_generate: false` and `verification: NOT_PERFORMED` within the graph result. Graph nodes are candidate content, not trusted semantic truths. The local SQLite prototype and registry token are not production authorization.

## Why SQL first, extensibility next

The compiler exposes an explicit typed `SemanticQueryPlan`. Future language surfaces (natural language, spreadsheet formulas, graphical filters, existing SQL drivers) should compile to that same plan rather than duplicating the graph backend. The next increments are metadata projection, typed `WHERE` predicates, provenance inspection, semantic diff and versioned PackSpec resolution. Those are design steps, **not current features**.

## Tests

```sh
python -m unittest discover -s tools/semantic_store/tests -p test_semantic_sql.py -v
python -m unittest discover -s tools/semantic_store/tests -p 'test_*.py' -v
```

The existing Semantic Store workflow's prototype job includes all `test_*.py` tests.
