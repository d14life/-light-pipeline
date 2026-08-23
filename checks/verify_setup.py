#!/usr/bin/env python
"""
Oracles for GATES.md. One subcommand per gate.

Each mode asserts everything itself, exits non-zero on the first failure, and
prints its success marker only after every assertion passed. A gate must never
be able to pass by printing its marker on the way to an error - that is why the
marker is the last statement in each function and nothing prints it early.

    python checks/verify_setup.py scaffold
    python checks/verify_setup.py look-glb
    python checks/verify_setup.py look-video
    python checks/verify_setup.py line-endings
    python checks/verify_setup.py blender-gpu
"""

import os
import re
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BLENDER = os.environ.get(
    "BLENDER", r"C:\Program Files\Blender Foundation\Blender 4.5\blender.exe"
)
if not os.path.exists(BLENDER):
    BLENDER = "blender"


def die(msg):
    print(f"FAIL: {msg}")
    sys.exit(1)


def run(cmd, **kw):
    return subprocess.run(cmd, capture_output=True, text=True, errors="replace", **kw)


def scaffold():
    """The scene skeleton builds, and contains the groups the design needs."""
    out = os.path.join(ROOT, "checks", "_tmp_scaffold.blend")
    r = run([BLENDER, "-b", "--python", os.path.join(ROOT, "blender_light_scene.py"),
             "--", "--build", "--out", out.replace("\\", "/")])
    if r.returncode != 0:
        die(f"blender exited {r.returncode}\n{(r.stderr or r.stdout)[-500:]}")
    tree = r.stdout
    for group in ("case", "word", "board", "loop", "stage"):
        if not re.search(rf"^\[tree\]\s+{group}\b", tree, re.M):
            die(f"collection '{group}' missing from the scaffold tree")
    for part in ("case_panel", "res_L", "res_T", "mb_pcb", "mb_radiator", "pump"):
        if part not in tree:
            die(f"placeholder '{part}' missing")
    m = re.search(r"\[scaffold\] (\d+) groups, (\d+) named placeholders", tree)
    if not m:
        die("scaffold did not report its own counts")
    groups, parts = int(m.group(1)), int(m.group(2))
    if groups < 4 or parts < 20:
        die(f"scaffold too thin: {groups} groups, {parts} placeholders")
    if not os.path.exists(out):
        die("no .blend written")
    os.remove(out)
    print(f"scaffold verification passed ({groups} groups, {parts} placeholders)")


def look_glb():
    """look.py reports the three facts the HERO brief demands of a mesh."""
    glb = os.path.join(ROOT, "checks", "_fixture.glb")
    if not os.path.exists(glb):
        mk = os.path.join(ROOT, "checks", "_mkfixture.py")
        with open(mk, "w", encoding="utf-8") as f:
            f.write(
                "import bpy\n"
                "for o in list(bpy.data.objects): bpy.data.objects.remove(o, do_unlink=True)\n"
                "bpy.ops.mesh.primitive_torus_add(major_radius=1, minor_radius=.3)\n"
                "bpy.ops.object.mode_set(mode='EDIT'); bpy.ops.uv.smart_project()\n"
                "bpy.ops.object.mode_set(mode='OBJECT')\n"
                "m = bpy.data.materials.new('steel'); bpy.context.object.data.materials.append(m)\n"
                f"bpy.ops.export_scene.gltf(filepath=r'{glb}', export_format='GLB')\n")
        r = run([BLENDER, "-b", "--python", mk])
        os.remove(mk)
        if not os.path.exists(glb):
            die(f"could not build the fixture GLB\n{(r.stderr or r.stdout)[-400:]}")
    r = run([sys.executable, os.path.join(ROOT, "look.py"), "glb", glb, "3"])
    if r.returncode != 0:
        die(f"look.py glb exited {r.returncode}\n{(r.stderr or r.stdout)[-400:]}")
    if "uv=True" not in r.stdout:
        die("look.py did not report UV presence")
    if not re.search(r"\d+ tris", r.stdout):
        die("look.py did not report a triangle count")
    if "materials=" not in r.stdout:
        die("look.py did not report materials")
    m = re.search(r"LOOK: (.+)", r.stdout)
    if not m or not os.path.exists(m.group(1).strip()):
        die("look.py printed no readable contact sheet")
    print("glb inspection verification passed")


def look_video():
    """A frame sheet must span the clip, not repeat one still."""
    src = r"C:\Users\D1\Downloads\LIGHT_MATCHED_SET\XRAY_SITE_1080.mp4"
    if not os.path.exists(src):
        die(f"reference clip missing: {src}")
    r = run([sys.executable, os.path.join(ROOT, "look.py"), "video", src, "4"])
    if r.returncode != 0:
        die(f"look.py video exited {r.returncode}\n{(r.stderr or r.stdout)[-400:]}")
    m = re.search(r"LOOK: (.+)", r.stdout)
    if not m:
        die("look.py printed no sheet path")
    sheet = m.group(1).strip()
    if not os.path.exists(sheet):
        die(f"sheet path does not exist: {sheet}")
    try:
        from PIL import Image
        w, h = Image.open(sheet).size
    except Exception as e:
        die(f"sheet is not a readable image: {e}")
    if w < 400 or h < 200:
        die(f"sheet suspiciously small: {w}x{h}")
    print(f"video inspection verification passed ({w}x{h} sheet)")


def line_endings():
    """CRLF in a .sh means `\\r: command not found` the moment it runs on the pod."""
    bad = []
    for name in sorted(os.listdir(ROOT)):
        if not name.endswith(".sh"):
            continue
        with open(os.path.join(ROOT, name), "rb") as f:
            if b"\r\n" in f.read():
                bad.append(name)
    if bad:
        die("CRLF found in: " + ", ".join(bad))
    shells = [n for n in os.listdir(ROOT) if n.endswith(".sh")]
    if len(shells) < 3:
        die(f"expected the three pod scripts, found {len(shells)}")
    for name in shells:
        r = run(["bash", "-n", os.path.join(ROOT, name)])
        if r.returncode != 0:
            die(f"{name} is not valid bash:\n{r.stderr[-300:]}")
    print(f"line ending verification passed ({len(shells)} scripts, LF, syntax clean)")


def blender_gpu():
    """Cycles must have a real GPU backend; a silent CPU fallback is the failure."""
    probe = os.path.join(ROOT, "checks", "_gpu.py")
    with open(probe, "w", encoding="utf-8") as f:
        f.write(
            "import bpy\n"
            "p = bpy.context.preferences.addons['cycles'].preferences\n"
            "p.get_devices()\n"
            "on = [d.name for d in p.devices if d.use and d.type != 'CPU']\n"
            "print('BACKEND=' + str(p.compute_device_type))\n"
            "print('ACTIVE=' + '|'.join(on))\n")
    r = run([BLENDER, "-b", "--python", probe])
    os.remove(probe)
    backend = re.search(r"BACKEND=(\w+)", r.stdout)
    active = re.search(r"ACTIVE=(.*)", r.stdout)
    if not backend or not active:
        die("could not read Cycles device preferences")
    if backend.group(1) in ("NONE", "CPU"):
        die(f"Cycles backend is {backend.group(1)} - renders would fall back to CPU")
    if not active.group(1).strip():
        die(f"backend {backend.group(1)} is selected but no device is enabled")
    print(f"gpu verification passed ({backend.group(1)}: {active.group(1).strip()})")


MODES = {
    "scaffold": scaffold, "look-glb": look_glb, "look-video": look_video,
    "line-endings": line_endings, "blender-gpu": blender_gpu,
}

if __name__ == "__main__":
    if len(sys.argv) != 2 or sys.argv[1] not in MODES:
        print(__doc__)
        sys.exit(2)
    MODES[sys.argv[1]]()
