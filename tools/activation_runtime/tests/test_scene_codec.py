import copy
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from tools.activation_runtime.scene_codec import train_model, encode, decode, decode_frames, frames, segment_index


@unittest.skipUnless(shutil.which("ffmpeg"), "FFmpeg not installed")
class SceneCodecTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name)
        self.source = root/"source.mkv"
        subprocess.run(["ffmpeg","-nostdin","-v","error","-n","-f","lavfi","-i",
                        "testsrc2=size=64x64:rate=4","-t","1","-c:v","ffv1",str(self.source)],
                       check=True, capture_output=True, timeout=20)
        self.model = train_model([self.source])
        self.payload, self.receipt = encode(self.source, self.model)

    def test_actual_playable_decode_and_seek(self):
        expected = frames(self.source)["frames"]
        self.assertEqual(decode_frames(self.payload,self.model), expected)
        self.assertEqual(decode_frames(self.payload,self.model,start=2,stop=3), expected[2:3])
        target = Path(self.temp.name)/"decoded.mkv"
        receipt = decode(self.payload,self.model,target)
        self.assertEqual(frames(target)["frames"], expected)
        self.assertEqual(receipt["decoded_frames"],4)
        self.assertGreater(self.receipt["payload_bytes"],0)
        self.assertEqual(segment_index(self.payload)[2]["time"],"1/2")

    def test_residual_missing_reordered_and_wrong_model_refuse(self):
        changed = copy.deepcopy(self.payload)
        changed["frames"].pop()
        with self.assertRaises(ValueError):
            decode_frames(changed,self.model)
        changed = copy.deepcopy(self.payload)
        changed["frames"].reverse()
        with self.assertRaises(ValueError):
            decode_frames(changed,self.model)
        changed = copy.deepcopy(self.payload)
        changed["frames"][0]["data"]="AAAA"
        with self.assertRaises(ValueError):
            decode_frames(changed,self.model)
        model=copy.deepcopy(self.model)
        model["palette"][0][0] ^= 1
        with self.assertRaises(ValueError):
            decode_frames(self.payload,model)

    def test_deterministic_payload(self):
        other,_=encode(self.source,self.model)
        self.assertEqual(other,self.payload)


@unittest.skipUnless(shutil.which("ffmpeg"), "FFmpeg not installed")
class AudioCaptionTests(unittest.TestCase):
    def test_actual_audio_caption_pixels_and_timing_survive_playable_decode(self):
        with tempfile.TemporaryDirectory() as temp:
            source=Path(temp)/"caption-source.mkv"
            subprocess.run(["ffmpeg","-nostdin","-v","error","-n","-f","lavfi","-i",
                "color=c=black:size=96x64:rate=4","-f","lavfi","-i","sine=frequency=440:sample_rate=16000",
                "-vf","drawtext=text=NOT EXCEPT:fontcolor=white:fontsize=10:x=3:y=3","-t","1",
                "-c:v","ffv1","-c:a","pcm_s16le",str(source)],check=True,capture_output=True,timeout=20)
            model=train_model([source]);payload,_=encode(source,model)
            target=Path(temp)/"decoded.mkv"
            result=decode(payload,model,target)
            self.assertEqual(result["decoded_frames"],4)
            self.assertEqual(frames(target)["frames"],frames(source)["frames"])
            bad=copy.deepcopy(payload);bad["source_frame_pts"][1]="0.3"
            with self.assertRaises(ValueError):decode(bad,model,Path(temp)/"bad-timing.mkv")


class DecoderVariantTests(unittest.TestCase):
    def test_scalar_and_strided_decoders_are_byte_identical(self):
        import base64,zlib
        from hashlib import sha256
        from tools.activation_runtime.scene_codec import digest
        model={"schema":"qualityrag.scene-palette/v1","algorithm":"flat-backdrop-rgb-xor/v1","palette":[[1,2,3]],"training_sources":[]}
        original=bytes(range(12));residual=bytes(value ^ model["palette"][0][i%3] for i,value in enumerate(original))
        payload={"schema":"qualityrag.scene-video/v1","codec":"scene-palette-rgb/v1","runtime_abi":"python-scene-reference/v1",
            "model_sha256":digest(model),"width":2,"height":2,"frame_count":1,"frames":[{"index":0,"backdrop":0,
            "mode":"xor-zlib","data":base64.b64encode(zlib.compress(residual)).decode(),"frame_sha256":sha256(original).hexdigest()}]}
        self.assertEqual(decode_frames(payload,model,implementation="scalar"),decode_frames(payload,model,implementation="strided"))
        with self.assertRaises(ValueError):decode_frames(payload,model,implementation="unknown")
