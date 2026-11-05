"""Observed local producer/consumer playback, not simulated network performance."""
from hashlib import sha256
from pathlib import Path
from queue import Queue, Empty, Full
from threading import Event, Thread, Timer
from time import perf_counter_ns, monotonic
import subprocess


def _play(produce, *, frame_count, fps, buffer_frames=2):
    if (type(frame_count) is not int or not 1<=frame_count<=120 or not 0<fps<=30 or frame_count/fps>10
            or type(buffer_frames) is not int or not 1<=buffer_frames<=8):
        raise ValueError("Bounded playback profile required")
    queue=Queue(maxsize=buffer_frames);stop=Event();errors=[]
    started=perf_counter_ns()
    def publish(frame):
        while not stop.is_set():
            try:queue.put(frame,timeout=.05);return
            except Full:continue
        raise ValueError("Playback stopped")
    def worker():
        try:produce(publish,stop)
        except Exception as exc:errors.append(type(exc).__name__)
    thread=Thread(target=worker,daemon=True);thread.start()
    hashes=[];waits=[];startup=None;deadline=None
    try:
        for index in range(frame_count):
            if deadline is not None:
                stop.wait(max(0,deadline-monotonic()))
            try:frame=queue.get_nowait();wait_ns=0
            except Empty:
                wait_start=perf_counter_ns()
                try:frame=queue.get(timeout=5)
                except Empty as exc:raise ValueError("Playback unavailable or stalled") from exc
                wait_ns=perf_counter_ns()-wait_start
            if not isinstance(frame,bytes) or not frame:raise ValueError("Missing decoded frame")
            if index==0:startup=perf_counter_ns()-started
            else:waits.append(wait_ns)
            hashes.append(sha256(frame).hexdigest())
            deadline=monotonic()+1/fps
    finally:
        stop.set();thread.join(6)
    if thread.is_alive() or errors:raise ValueError("Playback producer failed or exceeded bound")
    return {"startup_ns":startup,"buffer_wait_ns":sum(waits),
            "rebuffer_events":sum(v>0 for v in waits),"frame_waits_ns":waits,
            "observed_wall_ns":perf_counter_ns()-started,"buffer_capacity_frames":buffer_frames,
            "decoded_frame_sha256":hashes,"frames":len(hashes)}


def benchmark_playback(session_factory, baseline_path, *, indices):
    """Play both actual decoders with the same two-frame queue and cadence.

    Startup includes session/process initialization. Rebuffer time is measured
    only when the consumer actually finds its queue empty after the next-frame
    deadline. Both arms use local inputs; no WAN/device advantage is inferred.
    """
    from fractions import Fraction
    from .scene_codec import frames
    from .streaming import benchmark_seek
    baseline=Path(baseline_path)
    item=frames(baseline)
    if not any(s.get("codec_name")=="av1" for s in item["metadata"]["streams"]):
        raise ValueError("Actual AV1 baseline required")
    count=len(item["frames"]);fps=float(Fraction(item["fps"]))
    # Refuse the wrong baseline before attributing any speed difference.
    session=session_factory()
    header=session.index["header"]
    if (header["frame_count"],header["width"],header["height"],Fraction(header["fps"])) != \
       (count,item["width"],item["height"],Fraction(item["fps"])):
        raise ValueError("Baseline playback profile differs")
    def reference(publish,stop):
        active=session_factory()
        for index in range(count):
            if stop.is_set():return
            row=active.seek(index,index+1)
            if row["action"]!="PLAY":raise ValueError("Signed reference playback refused")
            publish(row["frames"][0])
    def av1(publish,stop):
        child=subprocess.Popen(["ffmpeg","-nostdin","-v","error","-i",str(baseline),
            "-map","0:v:0","-pix_fmt","rgb24","-fps_mode","passthrough","-f","rawvideo","-"],
            stdout=subprocess.PIPE,stderr=subprocess.DEVNULL)
        killer=Timer(20,child.kill);killer.start()
        size=item["width"]*item["height"]*3
        try:
            for _ in range(count):
                frame=child.stdout.read(size)
                if len(frame)!=size:raise ValueError("Short baseline frame")
                publish(frame)
            if child.stdout.read(1) or child.wait(timeout=5):raise ValueError("Baseline decoder failed")
        finally:
            killer.cancel()
            if child.poll() is None:child.kill()
            child.wait(timeout=5);child.stdout.close()
    arms={"reference":_play(reference,frame_count=count,fps=fps),
          "av1":_play(av1,frame_count=count,fps=fps)}
    matched=arms["reference"]["decoded_frame_sha256"]==arms["av1"]["decoded_frame_sha256"]
    return {"schema":"qualityrag.playback-benchmark/v1","scope":"LOCAL_BOUNDED_PLAYBACK",
            "baseline_sha256":sha256(baseline.read_bytes()).hexdigest(),"arms":arms,
            "exact_frame_match":matched,"comparison_qualified":matched,
            "fidelity_scope":"DECODED_RGB_FRAMES_ONLY",
            "seek":benchmark_seek(session_factory,baseline,indices),
            "network_performance":"UNMEASURED","physical_device_performance":"UNMEASURED",
            "performance_advantage":"NOT_ESTABLISHED"}
