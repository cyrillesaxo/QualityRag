# Signed streaming index boundaries

US-033's local frame-streaming reference now validates its index before fetching
frames or allocating frame placeholders. A signature authenticates the issuer
and supplied bytes; it cannot exempt a release from runtime resource limits.

The index must have the supported schema, exact reference/raw variant inventory,
a compatible normalized RGB header and matching model hashes. Frame count is
limited to 120, dimensions to 512 by 512, total normalized RGB data to 24 MB,
rate to 30 fps and duration to 10 seconds. Integers exclude booleans. Each segment
has the expected ordered integer index, matching model dependency and pinned
variant/frame hashes. Every frame has a bounded rational timestamp string.
Timelines must be nonnegative, strictly increasing and within the encoder's
one-millisecond constant-frame-rate tolerance. Original timestamp strings are
returned unchanged. This checks timeline consistency, not external source truth.

release refuses an index/address mismatch and unsupported sequence values.
StreamSession checks the host minimum sequence, signature lifetime, trusted keys,
tenant, policy, source, model and current decoder binding. Object parsing rejects
duplicate JSON keys and nonfinite values within the store's two-million-byte
limit. Index validation occurs before segment placeholder allocation, including
for malformed indexes signed by an otherwise trusted issuer.

## Startup and fallback

~~~python
opened = open_stream(store, signed_release=signed_release, keys=trusted_keys,
    expected_policy_sha256=policy_hash, minimum_sequence=host_floor,
    as_of=host_time, fallback_ref=host_authorized_baseline)
if opened["action"] == "READY":
    result = opened["session"].seek(start, stop, variant="reference")
else:
    # Route to opened["reference"] through the host's authorized fallback player.
    result = opened
~~~

open_stream returns READY with a local StreamSession or FALLBACK with no session.
Missing/corrupt index/model state, malformed contracts, expired/revoked signatures,
policy mismatch and below-floor releases select the host-supplied fallback.
The wrapper does not fetch or authorize that fallback, or generate replacement
frames. Direct StreamSession construction still raises on startup refusal.

A missing, corrupt or malformed requested frame selects FALLBACK, returns no
frames and leaves playback position unchanged. Invalid caller seek ranges still
raise. Paused sessions remain paused. Only index/model objects are fetched at
startup; requested frame objects are fetched on seek. The index includes the
existing audio/header fields, so this is not an adaptive audio-streaming or
network-byte optimality claim. Reference and raw are equivalent decoded frame
representations, not perceptual bitrate levels.

## Verification and limits

~~~bash
python -m unittest discover -s tools/activation_runtime/tests -p 'test_streaming*.py' -v
~~~

Tests exercise signed malformed indexes, huge counts, incorrect types, missing or
reordered segments, invalid dependencies, malformed timing, exact timestamp
retention, strict version floors, corrupted records, startup fallback and bounded
random access. Real network startup/buffering, conventional player comparison and
physical mobile/TV performance remain unmeasured acceptance gates.
