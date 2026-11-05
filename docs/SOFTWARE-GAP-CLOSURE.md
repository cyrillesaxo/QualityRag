# Streaming measurements and pinned agent evaluation

This change supplies the three software criteria left incomplete by the
verification at `d78d9fb0f5e9c30077928cdddff08cd00fa4a1e7`.

## US-033: startup, buffering and seek

`tools.activation_runtime.playback_benchmark.benchmark_playback` accepts a
host-configured signed `StreamSession` factory, an actual AV1 baseline path,
and bounded seek indices. It returns measurements from both actual decoders:

- Initialization to first decoded frame (`startup_ns`).
- Time the consumer actually waits for an empty frame buffer after its next
  frame deadline (`buffer_wait_ns`, `frame_waits_ns`, `rebuffer_events`).
- Bounded queue capacity and decoded frame hashes.
- The existing fresh-session/fresh-FFmpeg seek measurements.

Both arms use the same two-frame queue, frame count and playback cadence.
The AV1 arm reads real FFmpeg output; the reference arm verifies and decodes
the signed segments. A non-AV1 baseline or mismatching dimensions/rate is
rejected. Differing decoded frames make `comparison_qualified=false`.

This is **local bounded playback**. It does not measure WAN transport or
physical phone/TV performance, or establish a performance advantage. Queue
waits are observed wall-clock waits, not inferred network latency. A delayed
producer regression test proves that a real late frame registers a stall.

```python
from tools.activation_runtime.playback_benchmark import benchmark_playback

# session_factory creates a StreamSession with host-provided custody, trusted
# public keys, signed release, policy hash and minimum sequence.
receipt = benchmark_playback(session_factory, "baseline-av1.mkv", indices=[0, 2])
```

## US-038: uniform proposals and evaluation pins

All six roles now return a top-level `patches` list, parent grammar hash and
rationale. Non-editing roles explicitly return an empty patch list. These
remain unverified proposals and cannot promote or generate.

Each request pins the bytes of `agents.py`, `agent_worker.py`,
`process_sandbox.py`, `common.py`, its versioned role schema, the Python
runtime version and the exact finite task dataset. The worker independently
recomputes the pins **before** installing its syscall sandbox and executing
the task. Changed task input or any stale code pin is refused. The parent
also requires the returned pin to match its request.

The task dataset is the exact bounded input to the deterministic role, such
as counterexample cases. It is not an external corpus or permission to
disclose held-out datasets. This does not establish LLM novelty or semantic
truth. The host filesystem and interpreter remain trusted; the pin does not
defend against a privileged administrator replacing the running process.

## Reproduce

```bash
python -m unittest discover -s tools/activation_runtime/tests -p 'test_agent_pins.py' -v
python -m unittest discover -s tools/activation_runtime/tests -p 'test_playback_benchmark.py' -v
```

The playback check needs FFmpeg/ffprobe with the AV1 encoder. CI installs the
required media stack. Its generated pattern is owned test data, not a
representative licensed research corpus.
