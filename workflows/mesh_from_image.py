#!/usr/bin/env python
"""
Cut-out image -> textured GLB, via Pixal3D. Runs on the pod.

    python workflows/cutout.py output/ref_fan.png input/fan_cut.png
    python workflows/mesh_from_image.py fan_cut.png fan_120

Four things in here were each found by looking at a wrong mesh, not by reading
docs. In order of how much damage they do:

1. `camera_mode=moge` plus a visible floor puts a SLAB OF GEOMETRY behind the
   subject. MoGe estimates the camera from RGB and never sees the alpha, so a
   backdrop still present there becomes a wall it reconstructs. cutout.py now
   flattens the background to one colour, which leaves MoGe nothing to find.

2. Switching to `camera_mode=manual` removes the slab and RUINS THE DEPTH - the
   default angle and distance do not match a three-quarter product shot, and
   the mesh collapses to a plate. Keep moge, fix the image instead.

3. ComfyUI's LoadImage splits RGBA into IMAGE and MASK, and its MASK is the
   INVERSE of alpha (measured: 70.8% white for a subject covering 29.2%), so
   the alpha has to be rebuilt with InvertMask + JoinImageWithAlpha before
   `background_mode=keep_alpha` will accept it.

4. Pixal3D hardcodes briaai/RMBG-2.0, which is CC BY-NC. `load_rembg=False`
   plus a BiRefNet (MIT) cut-out keeps the licence clean, at the cost of doing
   the cut-out in a separate step.
"""

import json
import sys
import time
import urllib.request

API = "http://127.0.0.1:3000"


def post(path, payload=None):
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(API + path, data=data,
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.load(r)


def graph(image_name, out_prefix, seed=7, tris=200000, texture=2048):
    return {
        "1": {"class_type": "LoadImage", "inputs": {"image": image_name}},
        # rebuild alpha: LoadImage's mask is 1-alpha
        "2": {"class_type": "InvertMask", "inputs": {"mask": ["1", 1]}},
        "3": {"class_type": "JoinImageWithAlpha",
              "inputs": {"image": ["1", 0], "alpha": ["2", 0]}},
        "4": {"class_type": "Pixal3DModelLoader", "inputs": {
            "model_repo": "TencentARC/Pixal3D",
            "hf_endpoint": "https://huggingface.co",
            "attention_backend": "auto", "vram_mode": "dynamic_vram",
            # the weights are already on the volume; True would re-fetch 23 GB
            "download_if_missing": False,
            "load_moge": True,
            "load_rembg": False,          # BiRefNet did it, and RMBG is CC BY-NC
            "naf_mode": "fallback_if_missing",   # HAS_LIBNATTEN is False here
            "naf_target_size": "upstream",
            "preload_naf": False, "force_reload": False}},
        "5": {"class_type": "Pixal3DImageTo3D", "inputs": {
            "model": ["4", 0], "image": ["3", 0], "seed": seed,
            "pipeline_type": "1024_cascade",
            "background_mode": "keep_alpha",
            "camera_mode": "moge",        # see note 2 - manual wrecks the depth
            "manual_camera_angle_x": 0.857556, "manual_distance": 2.0,
            "mesh_scale": 1.0, "extend_pixel": 0, "camera_resolution": 512,
            "steps": 12, "guidance": 7.5, "texture_guidance": 1.0,
            "max_num_tokens": 49152, "force_offload": True}},
        # 200k/2048 here, not the 1M/4096 defaults: conditioning/to_web.py takes
        # it to the web budget afterwards, and a first look does not need 1M.
        "6": {"class_type": "Pixal3DExportGLB", "inputs": {
            "pixal3d_result": ["5", 0], "decimation_target": tris,
            "texture_size": texture, "remesh": True,
            "filename_prefix": "prop_" + out_prefix}},
    }


def main():
    if len(sys.argv) < 3:
        print(__doc__)
        return 2
    image_name, prefix = sys.argv[1], sys.argv[2]
    seed = int(sys.argv[3]) if len(sys.argv) > 3 else 7

    pid = post("/prompt", {"prompt": graph(image_name, prefix, seed)})["prompt_id"]
    print("[queue] " + pid, flush=True)

    t0 = time.time()
    while True:
        time.sleep(5)
        hist = post("/history/" + pid)
        if pid in hist:
            break
        if time.time() - t0 > 1800:
            print("!! 30 min with no result")
            return 1

    e = hist[pid]
    st = e.get("status", {})
    if st.get("status_str") == "error":
        for m in st.get("messages", []):
            if m[0] == "execution_error":
                d = m[1]
                print("!! FAILED in " + str(d.get("node_type")))
                print("   " + str(d.get("exception_message"))[:400])
                return 1
        return 1

    print("[done] %ds" % int(time.time() - t0))
    for out in e.get("outputs", {}).values():
        if "text" in out:
            print("GLB: " + str(out["text"][0]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
