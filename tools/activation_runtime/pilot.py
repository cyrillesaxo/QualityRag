"""Real host measurements with explicit unavailable device/power evidence."""
import os
import platform
from pathlib import Path
import resource
from time import perf_counter_ns,process_time_ns
import tracemalloc

from .scene_codec import decode_frames


def energy_counter():
    paths=sorted(Path("/sys/class/powercap").glob("intel-rapl*/energy_uj"))
    if not paths:return None
    try:return sum(int(path.read_text()) for path in paths)/1_000_000
    except (OSError,ValueError):return None


def measure(payload,model,*,device_class,max_memory_bytes,max_latency_ns,max_energy_j=None):
    if device_class not in {"host-cpu","mobile","tv"}:raise ValueError("Declared supported device class required")
    if any(type(v) is not int or v<1 for v in (max_memory_bytes,max_latency_ns)):raise ValueError("Positive device budgets")
    # Do not silently impersonate mobile or TV hardware from a server process.
    if device_class!="host-cpu":
        return {"status":"UNKNOWN","reason":"PHYSICAL_DEVICE_AGENT_REQUIRED","device_class":device_class,
                "action":"FALLBACK","measurements":None}
    import subprocess
    import sys
    from .scene_codec import canon
    if max_memory_bytes<64_000_000:
        return {"status":"RESOURCE_LIMIT","action":"FALLBACK","reason":"RUNTIME_MEMORY_FLOOR"}
    before_energy=energy_counter()
    start=perf_counter_ns()
    try:
        child=subprocess.run([sys.executable,str(Path(__file__).with_name("decode_worker.py"))],
            input=canon({"payload":payload,"model":model,"cpu_seconds":2,"memory_bytes":max_memory_bytes}),
            capture_output=True,timeout=max_latency_ns/1_000_000_000,
            env={"PATH":os.environ.get("PATH","/usr/bin:/bin")},close_fds=True)
    except subprocess.TimeoutExpired:
        return {"status":"RESOURCE_LIMIT","action":"FALLBACK","reason":"WALL_CLOCK_LIMIT"}
    import json
    if child.returncode or len(child.stdout)>65536:
        return {"status":"RESOURCE_LIMIT_OR_INVALID","action":"FALLBACK","reason":"HARD_CPU_MEMORY_OR_COMPATIBILITY_LIMIT"}
    observed=json.loads(child.stdout)
    latency=perf_counter_ns()-start
    after_energy=energy_counter()
    energy=None if before_energy is None or after_energy is None or after_energy<before_energy else after_energy-before_energy
    failed=latency>max_latency_ns or (max_energy_j is not None and (energy is None or energy>max_energy_j))
    return {"schema":"qualityrag.device-pilot/v1","status":"LIMIT_EXCEEDED_OR_UNMEASURED" if failed else "HOST_MEASURED",
            "action":"FALLBACK" if failed else "RESEARCH_PLAYBACK","device_class":device_class,
            "platform":platform.system(),"machine":platform.machine(),"python":platform.python_version(),
            "cold_process_ns":latency,**observed,"frames":len(observed["frame_hashes"]),"energy_j":energy,
            "thermal_throttling":"UNMEASURED","supported_mobile_tv_claim":False,"can_generate":False,
            "hard_limits":"RLIMIT_AS_RLIMIT_CPU_SECCOMP_AND_PARENT_TIMEOUT"}
