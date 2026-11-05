"""Offline CompressAI factorized per-frame baseline with pinned licensed weights.

No model downloads, pickle code loading or arbitrary model names. This is a
learned image codec applied independently to frames, not a temporal video codec.
A qualified comparison must still match the PackSpec fidelity obligations.
"""
from hashlib import sha256
from pathlib import Path


def benchmark(source,*,checkpoint,checkpoint_sha256,license_ref):
    path=Path(checkpoint)
    if not license_ref or not path.is_file() or sha256(path.read_bytes()).hexdigest()!=checkpoint_sha256:
        raise ValueError("Licensed hash-pinned offline checkpoint required")
    try:
        import torch
        from compressai.zoo import bmshj2018_factorized
    except ImportError as exc:
        raise RuntimeError("NEURAL_CODEC_DEPENDENCY_UNAVAILABLE") from exc
    from .scene_codec import frames
    from time import perf_counter_ns
    torch.set_num_threads(1)
    model=bmshj2018_factorized(quality=1,pretrained=False)
    model.load_state_dict(torch.load(path,map_location="cpu",weights_only=True))
    model.eval();model.update(force=True)
    item=frames(source);measurements=[]
    with torch.no_grad():
        for frame in item["frames"]:
            x=torch.tensor(list(frame),dtype=torch.float32).reshape(item["height"],item["width"],3).permute(2,0,1).unsqueeze(0)/255
            pad_h=(-item["height"])%64;pad_w=(-item["width"])%64
            x=torch.nn.functional.pad(x,(0,pad_w,0,pad_h))
            start=perf_counter_ns();coded=model.compress(x);encode_ns=perf_counter_ns()-start
            start=perf_counter_ns();decoded=model.decompress(coded["strings"],coded["shape"])["x_hat"];decode_ns=perf_counter_ns()-start
            decoded=decoded[:,:,:item["height"],:item["width"]].clamp(0,1).mul(255).round().to(torch.uint8).squeeze(0).permute(1,2,0).contiguous()
            exact=bytes(decoded.flatten().tolist())==frame
            measurements.append({"bytes":sum(len(s) for group in coded["strings"] for s in group),
                                 "encode_ns":encode_ns,"decode_ns":decode_ns,"exact_rgb":exact})
    return {"schema":"qualityrag.neural-intraframe-baseline/v1","model":"bmshj2018_factorized-quality1",
            "checkpoint_sha256":checkpoint_sha256,"model_bytes":path.stat().st_size,"license_ref":license_ref,
            "frames":measurements,"qualified_for_exact_profile":all(r["exact_rgb"] for r in measurements),
            "profile_boundary":"A lossy neural result cannot qualify for an exact preservation contract",
            "temporal_codec":False,"can_generate":False}
