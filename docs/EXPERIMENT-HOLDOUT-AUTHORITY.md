# Experiment holdout authorization and statistical work bounds

The experiment registry records protocols and authenticated opening events. A
caller-supplied role label cannot authorize an opening. The registry does not
serve corpus bytes, prove that a human evaluator is independent, or certify that
source files have never been viewed outside this process. Those remain separate
host controls and research acceptance requirements.

## Register before opening

Configure Registry with a durable SQLite file, a unique registry_id, a tenant,
the proposer's public key, trusted evaluator public keys, and a key-ID-to-subject
map. These are trusted host settings, never properties selected by a proposing
agent. Each key's subject is assigned by the host; a signer cannot choose another
actor name in its approval. Reload the registry with an updated trust map when
rotating or revoking keys. A proposer key cannot qualify as independent merely
by using another key ID.

~~~python
from tools.activation_runtime.experiments import Registry

registry = Registry(
    "research.sqlite",
    registry_id="your-unique-registry",
    tenant="your-tenant",
    reviewer_keys=evaluator_public_keys,
    reviewer_subjects=evaluator_key_subjects,
    author_public_key=proposer_public_key,
)
try:
    protocol_sha = registry.register(protocol)
    context = registry.holdout_context(
        protocol["id"], actor="assigned-evaluator", dataset_sha256=dataset_sha
    )
    # Send the context through the host's separate authorized review process.
    # The proposing process must not own an evaluator private key.
    protocol_to_evaluate = registry.open_holdout(
        protocol["id"], actor="assigned-evaluator", dataset_sha256=dataset_sha,
        signed_review=evaluator_signed_authorization,
    )
    receipt = registry.opening_receipt(protocol["id"])
finally:
    registry.close()
~~~

The evaluator uses the existing authority.review_binding format to sign that
exact context. It binds opening purpose, registry identity, tenant, actor,
protocol ID/hash, dataset hash and observed registration receipt hash. The host
clock checks signature validity; the caller cannot supply an as_of time to the
opening method. The protocol's declared registration time cannot be in the
future, and opening cannot predate the host-observed registration time.

The registry freezes all six hypotheses, comparators, metrics, rejection rules,
sample plan and corpus digest. It hashes the stored protocol again before use.
Observed registration and opening receipts are append-only. An opening stores the
signed envelope and nonce reservation atomically with its event. Failed writes
or caller rollbacks leave the approval reusable; concurrent workers cannot spend
one nonce twice. Each protocol opens once, and a nonce cannot open another
protocol. Proposers cannot substitute a role string or a different dataset.

The former role= API is intentionally unsupported. Legacy records without an
observed registration receipt are refused rather than silently grandfathered.
Previously exposed data does not become a blind holdout by assigning a new
protocol ID. It remains exploratory evidence; a genuinely fresh holdout and
independent registration/review are needed for a new controlled experiment.

SQLite owners, host clocks and the host trust configuration remain inside the
trust boundary. Keep durable receipts with backups; clearing or replacing the
registry is not a replay-safe recovery procedure. Local timestamps are observed
host times, not an externally attested timestamp service. Authored test keys and
passing CI do not satisfy corpus licensing, representative sampling or external
review acceptance.

## Paired resampling contract

paired_interval accepts 2–10,000 finite before/after observations, an integer
seed between 0 and 2**63-1, and 100–10,000 resamples. Total work is limited to
20,000,000 draws. These are implementation resource bounds, not a statistical
power or sample-size claim. Excess work, invalid seeds/counts, nonfinite inputs
and overflowing paired deltas refuse before returning a result.

Results retain the mean after-minus-before difference, percentile interval,
seed, resample count and draw count. Interpret the sign using the preregistered
metric direction. Supplied pairs do not establish independent scene families:
the result explicitly reports independence=CALLER_DECLARED_NOT_VERIFIED. Family
selection, annotation quality, uncertainty interpretation and final scientific
adjudication still require the registered design and appropriate reviewers.

## Verification

~~~bash
python -m unittest discover -s tools/activation_runtime/tests -p 'test_holdout_authority.py' -v
python -m unittest discover -s tools/activation_runtime/tests -p 'test_experiments.py' -v
~~~

Tests use real Ed25519 signatures and durable SQLite connections. They cover
subject/key/scope/expiry/revocation refusal, same-key proposer aliases, concurrent
replay, write failure/retry, outer rollback, immutable receipt restart, clock
regression, protocol corruption, legacy-record refusal and resampling budgets.
