#!/usr/bin/env python
"""
One hardware part, from a sentence to a textured GLB.

    python workflows/make_prop.py fan_120 "a 120mm PC case fan, black plastic frame, nine blades"

Runs on the pod against the local ComfyUI API. Two stages in one graph:

  FLUX.2 klein 4B  ->  an isolated part on flat grey
  Pixal3D          ->  mesh + PBR  ->  GLB

The prompt suffix is not decoration. Image-to-3D bakes whatever lighting is in
the picture straight into the albedo, and it reconstructs a shape from shading
cues - so the frame wants soft directional light (enough gradient to read a
chamfer) on a plain background (nothing to mistake for geometry), with the
whole object inside the frame (a cropped edge becomes a cut-off mesh).
"""

import json
import sys
import time
import urllib.error
import urllib.request

API = "http://127.0.0.1:3000"

FRAMING = (", single isolated object centred in frame, plain neutral mid-grey "
           "background, soft directional studio light, no cast shadow, no "
           "reflections, entire object fully visible, three-quarter view, "
           "sharp focus, product photograph")

NEGATIVE = "cropped, cut off, multiple objects, busy background, hard shadows, text, watermark"


def graph(name, prompt, seed, steps, res):
    """ComfyUI API-format graph. Node ids are strings; links are [id, slot]."""
    return {
        # ---------------- stage 1: the reference image ----------------
        "1": {"class_type": "UNETLoader",
              "inputs": {"unet_name": "flux-2-klein-4b.safetensors",
                         "weight_dtype": "default"}},
        "2": {"class_type": "CLIPLoader",
              "inputs": {"clip_name": "qwen_3_4b.safetensors", "type": "flux2"}},
        "3": {"class_type": "VAELoader",
              "inputs": {"vae_name": "flux2-vae.safetensors"}},
        "4": {"class_type": "CLIPTextEncode",
              "inputs": {"clip": ["2", 0], "text": prompt + FRAMING}},
        "5": {"class_type": "CLIPTextEncode",
              "inputs": {"clip": ["2", 0], "text": NEGATIVE}},
        "6": {"class_type": "EmptyFlux2LatentImage",
              "inputs": {"width": res, "height": res, "batch_size": 1}},
        "7": {"class_type": "KSampler",
              "inputs": {"model": ["1", 0], "positive": ["4", 0],
                         "negative": ["5", 0], "latent_image": ["6", 0],
                         "seed": seed, "steps": steps, "cfg": 4.0,
                         "sampler_name": "euler", "scheduler": "simple",
                         "denoise": 1.0}},
        "8": {"class_type": "VAEDecode",
              "inputs": {"samples": ["7", 0], "vae": ["3", 0]}},
        "9": {"class_type": "SaveImage",
              "inputs": {"images": ["8", 0], "filename_prefix": f"ref_{name}"}},

        # ---------------- stage 2: the mesh ----------------
        # download_if_missing stays False: the weights are already on the volume
        # and a silent re-download would be 23 GB nobody asked for.
        "10": {"class_type": "Pixal3DModelLoader",
               "inputs": {"model_repo": "TencentARC/Pixal3D",
                          "hf_endpoint": "https://huggingface.co",
                          "attention_backend": "auto",
                          "vram_mode": "dynamic_vram",
                          "download_if_missing": False,
                          "load_moge": True, "load_rembg": True,
                          # HAS_LIBNATTEN is False on this box, so strict NAF
                          # would hard-fail instead of degrading.
                          "naf_mode": "fallback_if_missing",
                          "naf_target_size": "upstream",
                          "preload_naf": False, "force_reload": False}},
        "11": {"class_type": "Pixal3DImageTo3D",
               "inputs": {"model": ["10", 0], "image": ["8", 0],
                          "seed": seed, "pipeline_type": "1024_cascade",
                          "background_mode": "auto_remove",
                          "camera_mode": "moge",
                          "manual_camera_angle_x": 0.857556,
                          "manual_distance": 2.0, "mesh_scale": 1.0,
                          "extend_pixel": 0, "camera_resolution": 512,
                          "steps": 12, "guidance": 7.5,
                          "texture_guidance": 1.0, "max_num_tokens": 49152,
                          "force_offload": True}},
        # decimation and texture size are deliberately NOT the 1M/4096 defaults:
        # conditioning/to_web.py takes it down to the web budget later, but a
        # first look does not need a million triangles to be judged.
        "12": {"class_type": "Pixal3DExportGLB",
               "inputs": {"pixal3d_result": ["11", 0],
                          "decimation_target": 200000, "texture_size": 2048,
                          "remesh": True, "filename_prefix": f"prop_{name}"}},
    }


def post(path, payload=None):
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(API + path, data=data,
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.load(r)


def main():
    if len(sys.argv) < 3:
        print(__doc__)
        return 2
    name, prompt = sys.argv[1], sys.argv[2]
    seed = int(sys.argv[3]) if len(sys.argv) > 3 else 42

    g = graph(name, prompt, seed, steps=20, res=1024)
    pid = post("/prompt", {"prompt": g})["prompt_id"]
    print(f"[queue] {pid}  {name}")

    t0 = time.time()
    last = ""
    while True:
        time.sleep(5)
        hist = post("/history/" + pid) if True else {}
        if pid in hist:
            break
        try:
            q = post("/queue")
            running = len(q.get("queue_running", []))
            pending = len(q.get("queue_pending", []))
            msg = f"[{int(time.time()-t0)}s] running={running} pending={pending}"
            if msg[8:] != last[8:]:
                print(msg, flush=True)
            last = msg
        except Exception:
            pass
        if time.time() - t0 > 1800:
            print("!! 30 min with no result - giving up")
            return 1

    entry = hist[pid]
    status = entry.get("status", {})
    if status.get("status_str") == "error":
        for m in status.get("messages", []):
            if m[0] == "execution_error":
                d = m[1]
                print(f"!! FAILED in {d.get('node_type')} ({d.get('node_id')})")
                print("   " + str(d.get("exception_message"))[:400])
                return 1
        print("!! failed:", json.dumps(status)[:400])
        return 1

    print(f"[done] {int(time.time()-t0)}s")
    for node, out in entry.get("outputs", {}).items():
        for img in out.get("images", []):
            print(f"   image  {img['subfolder']}/{img['filename']}")
        for k, v in out.items():
            if k != "images":
                print(f"   {k}: {str(v)[:200]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
