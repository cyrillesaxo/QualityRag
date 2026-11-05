"""Pure frame activation under OS memory/CPU/syscall restrictions."""
from hashlib import sha256
import json
from pathlib import Path
import resource
import sys
from time import perf_counter_ns,process_time_ns
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from tools.activation_runtime.scene_codec import decode_frames
from process_sandbox import sandbox

try:
    raw=sys.stdin.buffer.read(40_000_001)
    if len(raw)>40_000_000:raise ValueError("Frame payload budget")
    request=json.loads(raw)
    sandbox(request["cpu_seconds"],request["memory_bytes"])
    start=perf_counter_ns();cpu=process_time_ns()
    decoded=decode_frames(request["payload"],request["model"])
    result={"frame_hashes":[sha256(frame).hexdigest() for frame in decoded],
            "activation_ns":perf_counter_ns()-start,"cpu_ns":process_time_ns()-cpu,
            "maxrss_kib":resource.getrusage(resource.RUSAGE_SELF).ru_maxrss}
    sys.stdout.write(json.dumps(result))
except Exception:
    sys.stderr.write("DEVICE_ACTIVATION_REFUSED\n");sys.exit(2)
