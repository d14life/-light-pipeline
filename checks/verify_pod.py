#!/usr/bin/env python
"""
Oracles for GATES.pod.md. Runs ON THE POD, after bootstrap.sh.

Same contract as verify_setup.py: assert everything, exit non-zero on the first
failure, print the success marker only at the end.

The point of these five is that every one of them has a plausible silent
failure. A download can "succeed" into a folder ComfyUI never scans. A gated
repo can be skipped while everything around it works. Cycles can quietly fall
back to CPU and just be slow. None of that raises an error anywhere.

    python checks/verify_pod.py blender
    python checks/verify_pod.py nodes
    python checks/verify_pod.py weights
    python checks/verify_pod.py layout
    python checks/verify_pod.py comfy-api
    python checks/verify_pod.py pixal-wheels
"""

import json
import os
import subprocess
import sys
import urllib.request

CU = os.environ.get("COMFY", "/workspace/ComfyUI")
MODELS = os.path.join(CU, "models")
COMFY_URL = os.environ.get("COMFYUI_URL", "http://127.0.0.1:3000")


def die(msg):
    print(f"FAIL: {msg}")
    sys.exit(1)


def run(cmd, **kw):
    return subprocess.run(cmd, capture_output=True, text=True, errors="replace", **kw)


def find(root, needle, min_gb=0.0):
    """Largest file whose name contains `needle`, ignoring the hf cache.

    Two traps here, both hit for real. `hf download --local-dir` leaves a
    .cache/huggingface tree of tiny metadata files named after their targets,
    so a first-match search finds a 0-byte stub next to a 27 GB checkpoint.
    And several files can share a needle (umt5 fp16 and fp8), so the largest
    is the one worth judging.
    """
    best, best_gb = None, 0.0
    for base, dirs, files in os.walk(root):
        dirs[:] = [d for d in dirs if not d.startswith(".")]
        for f in files:
            if needle.lower() not in f.lower():
                continue
            p = os.path.join(base, f)
            try:
                gb = os.path.getsize(p) / 1e9
            except OSError:
                continue
            if gb > best_gb:
                best, best_gb = p, gb
    return (best, best_gb) if best_gb >= min_gb else (best, best_gb)


def blender():
    """Installed, matching the PC's LTS, and on a real GPU backend."""
    r = run(["blender", "--version"])
    if r.returncode != 0:
        die("blender not on PATH")
    ver = r.stdout.split("\n")[0].strip()
    if "4.5" not in ver:
        die(f"version mismatch: pod has '{ver}', the PC authors in 4.5 LTS - "
            "a .blend saved here may not open there")
    probe = "/tmp/_gpu_probe.py"
    with open(probe, "w") as f:
        f.write(
            "import bpy\n"
            "p = bpy.context.preferences.addons['cycles'].preferences\n"
            "p.get_devices()\n"
            "on = [d.name for d in p.devices if d.use and d.type != 'CPU']\n"
            "print('BACKEND=' + str(p.compute_device_type)); print('ACTIVE=' + '|'.join(on))\n")
    r = run(["blender", "-b", "--python", probe])
    os.remove(probe)
    backend = active = None
    for line in r.stdout.splitlines():
        if line.startswith("BACKEND="):
            backend = line.split("=", 1)[1].strip()
        if line.startswith("ACTIVE="):
            active = line.split("=", 1)[1].strip()
    if backend in (None, "NONE", "CPU") or not active:
        die(f"Cycles has no GPU device (backend={backend}, active={active!r}) - "
            "renders would silently run on CPU")
    print(f"blender verification passed ({ver}, {backend}: {active})")


def nodes():
    """Every custom node the pipeline needs is actually cloned."""
    cn = os.path.join(CU, "custom_nodes")
    if not os.path.isdir(cn):
        die(f"no custom_nodes dir at {cn}")
    need = ["ComfyUI-GGUF", "Pixal3D-ComfyUI", "ComfyUI-Trellis2", "ComfyUI-WanVideoWrapper"]
    have = os.listdir(cn)
    missing = [n for n in need if n not in have]
    if missing:
        die("missing custom nodes: " + ", ".join(missing))
    for n in need:
        if not os.listdir(os.path.join(cn, n)):
            die(f"{n} is an empty directory - the clone failed")
    print(f"custom node verification passed ({len(need)} present)")


def weights():
    """The big files exist AND are the right order of magnitude.

    Size matters: a gated repo that was not accepted can leave a tiny stub or
    an error page where a 35 GB checkpoint should be.
    """
    want = [
        ("flux2_dev_fp8mixed", 30.0, "FLUX.2 dev image model"),
        ("mistral_3_small_flux2_fp8", 15.0, "FLUX.2 text encoder"),
        ("wan2.2_i2v_high_noise", 20.0, "Wan high-noise expert"),
        ("wan2.2_i2v_low_noise", 20.0, "Wan low-noise expert"),
        ("umt5", 5.0, "Wan text encoder"),
    ]
    problems = []
    for needle, min_gb, label in want:
        p, gb = find(MODELS, needle, 0.0)
        if p is None:
            problems.append(f"{label}: not found ({needle})")
        elif gb < min_gb:
            problems.append(f"{label}: only {gb:.1f} GB, expected >= {min_gb} GB - "
                            "likely a gated-repo stub")
    # Pixal3D and DINOv3 are directories, not single files
    for sub, label in [("Pixal3D", "Pixal3D checkpoints"),
                       ("facebook", "DINOv3 image encoder")]:
        d = os.path.join(MODELS, sub)
        if not os.path.isdir(d):
            problems.append(f"{label}: {d} missing")
            continue
        total = 0.0
        for b, dd, fs in os.walk(d):
            dd[:] = [x for x in dd if not x.startswith(".")]
            for f in fs:
                try:
                    total += os.path.getsize(os.path.join(b, f))
                except OSError:
                    pass
        total /= 1e9
        if total < 0.5:
            problems.append(f"{label}: only {total:.2f} GB under {sub}/ - "
                            "gated licence probably not accepted")
    if problems:
        die("\n  ".join(problems))
    print(f"weight verification passed ({len(want)} checkpoints + 2 encoders, sizes sane)")


def layout():
    """Weights must sit where ComfyUI scans, not under models/split_files/."""
    stray = os.path.join(MODELS, "split_files")
    if os.path.isdir(stray):
        die(f"{stray} still exists - hf download preserved repo paths and ComfyUI "
            "will not scan there; the flatten step did not run")
    for sub in ("diffusion_models", "text_encoders", "vae"):
        d = os.path.join(MODELS, sub)
        if not os.path.isdir(d):
            die(f"{d} missing")
        if not [f for f in os.listdir(d) if f.endswith((".safetensors", ".gguf"))]:
            die(f"{sub}/ contains no model files")
    print("layout verification passed (no split_files, all scanned folders populated)")


def comfy_api():
    """ComfyUI is up and reports the models it can actually see."""
    try:
        with urllib.request.urlopen(f"{COMFY_URL}/object_info", timeout=20) as r:
            info = json.load(r)
    except Exception as e:
        die(f"ComfyUI API unreachable at {COMFY_URL}: {e}")
    seen = set()
    for node in info.values():
        for group in ("required", "optional"):
            for spec in (node.get("input", {}).get(group) or {}).values():
                if isinstance(spec, list) and spec and isinstance(spec[0], list):
                    seen.update(str(x) for x in spec[0])
    if not any("flux2" in s.lower() for s in seen):
        die("ComfyUI is running but lists no flux2 checkpoint - "
            "the weights are on disk in a place it does not scan")
    print(f"comfy api verification passed ({len(info)} node types, flux2 visible)")


def pixal_wheels():
    """The CUDA kernels Pixal3D needs, imported for real - not just pip-listed."""
    need = ["flex_gemm_ap", "cumesh_vb", "o_voxel_vb_ap", "drtk"]
    missing = []
    for mod in need:
        r = run([sys.executable, "-c", f"import {mod}"])
        if r.returncode != 0:
            missing.append(mod)
    attn = run([sys.executable, "-c", "import flash_attn"]).returncode == 0
    if missing:
        die("cannot import: " + ", ".join(missing) +
            "\n  run Pixal3D's Environment Check node - it names the prebuilt wheels")
    if not attn:
        die("flash_attn will not import; Pixal3D needs FlashAttention 2 or 3")
    print(f"pixal wheel verification passed ({len(need)} kernels + flash_attn import)")


MODES = {
    "blender": blender, "nodes": nodes, "weights": weights,
    "layout": layout, "comfy-api": comfy_api, "pixal-wheels": pixal_wheels,
}

if __name__ == "__main__":
    if len(sys.argv) != 2 or sys.argv[1] not in MODES:
        print(__doc__)
        sys.exit(2)
    MODES[sys.argv[1]]()
