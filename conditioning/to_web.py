#!/usr/bin/env python
"""
Turn a generated GLB into one a browser can actually load.

    python conditioning/to_web.py in.glb out.glb --tris 15000 --size-mm 120

Raw image-to-3D output is not a web asset. Pixal3D defaults to a decimation
target near a million triangles and a 4096 texture; the HERO brief's shipping
hero was 9k triangles and 94.6 KB. That gap is this script.

What it does, and why each step is here rather than optional:

  scale      Generated meshes arrive in an arbitrary normalised box. Without a
             real-world size, camera distance, depth of field and float height
             downstream are all meaningless.
  UVs        Missing UVs fail silently - the model loads and simply has no
             albedo, roughness, normal or AO. In three.js the AO map is also
             what gates specular occlusion, so without it every recess mirrors
             the whole environment.
  material   Generative PBR guesses class wrong; a moulded part comes back near
             metalness 0.7 and reads as painted metal. Dielectrics are forced
             to 0 by declared class, metals to 1.
  decimate   To the triangle budget, last, so the bake happens on dense geometry.

Two files come out. `out.glb` is plain and Blender can open it - that is the
one that goes into the scene. `out.web.glb` carries meshopt (and KTX2 when
KTX-Software is installed), which lands in extensionsRequired and makes the
file unreadable to Blender - that one only ever ships to the browser.
The final byte count is printed, because a payload is a number with what it
buys, never a silent 30 MB.

NOT DONE YET: baking an AO map. The brief calls it out as the map that gates
specular occlusion in three.js, so a mesh conditioned here still needs one
before it ships. Do not read this script's success as "web ready".
"""

import argparse
import os
import shutil
import subprocess
import sys

BLENDER = os.environ.get(
    "BLENDER", r"C:\Program Files\Blender Foundation\Blender 4.5\blender.exe"
)
if not os.path.exists(BLENDER):
    BLENDER = "blender"

# metalness by declared class. Anything not listed stays as generated.
DIELECTRIC = {"plastic", "white_plastic", "rubber", "pcb", "ceramic",
              "acrylic_coolant", "glass_fluid"}
METAL = {"aluminium", "steel", "copper"}

BL = r'''
import sys, bpy
argv = sys.argv[sys.argv.index("--")+1:]
src, dst, tris, size_mm, mat_class = argv[0], argv[1], int(argv[2]), float(argv[3]), argv[4]

for o in list(bpy.data.objects):
    bpy.data.objects.remove(o, do_unlink=True)
bpy.ops.import_scene.gltf(filepath=src)
meshes = [o for o in bpy.context.scene.objects if o.type == "MESH"]
if not meshes:
    print("[cond] !! no mesh in input"); sys.exit(3)

before = 0
for m in meshes:
    m.data.calc_loop_triangles(); before += len(m.data.loop_triangles)

# --- real-world scale -------------------------------------------------------
import mathutils
lo = mathutils.Vector((1e9,)*3); hi = mathutils.Vector((-1e9,)*3)
for m in meshes:
    for c in m.bound_box:
        w = m.matrix_world @ mathutils.Vector(c)
        lo = mathutils.Vector(map(min, lo, w)); hi = mathutils.Vector(map(max, hi, w))
span = max(hi - lo)
if span > 0 and size_mm > 0:
    k = (size_mm / 1000.0) / span
    for m in meshes:
        if m.parent is None:
            m.scale = tuple(s * k for s in m.scale)
    print(f"[cond] scaled x{k:.4f} -> longest axis {size_mm} mm")

bpy.context.view_layer.update()

for m in meshes:
    m.select_set(True)
bpy.context.view_layer.objects.active = meshes[0]

# --- UVs --------------------------------------------------------------------
made = 0
for m in meshes:
    if not m.data.uv_layers:
        bpy.context.view_layer.objects.active = m
        bpy.ops.object.mode_set(mode="EDIT")
        bpy.ops.mesh.select_all(action="SELECT")
        bpy.ops.uv.smart_project(angle_limit=1.15, island_margin=0.02)
        bpy.ops.object.mode_set(mode="OBJECT")
        made += 1
print(f"[cond] uv: {made} unwrapped, {len(meshes)-made} already had them")

# --- material class ---------------------------------------------------------
DIELECTRIC = {"plastic","white_plastic","rubber","pcb","ceramic","acrylic_coolant","glass_fluid"}
METAL = {"aluminium","steel","copper"}
fixed = []
if mat_class in DIELECTRIC or mat_class in METAL:
    target = 0.0 if mat_class in DIELECTRIC else 1.0
    for m in meshes:
        for slot in m.material_slots:
            mat = slot.material
            if not mat or not mat.use_nodes: continue
            for n in mat.node_tree.nodes:
                if n.type == "BSDF_PRINCIPLED":
                    was = n.inputs["Metallic"].default_value
                    if abs(was - target) > 0.01:
                        n.inputs["Metallic"].default_value = target
                        fixed.append(f"{mat.name} {was:.2f}->{target:.0f}")
                    if mat_class in DIELECTRIC:
                        n.inputs["IOR"].default_value = 1.538
    if fixed:
        print(f"[cond] metalness corrected ({mat_class}): " + "; ".join(fixed[:4]))
    else:
        print(f"[cond] metalness already correct for {mat_class}")
else:
    print(f"[cond] material class '{mat_class}' not declared - metalness left as generated")

# --- decimate ---------------------------------------------------------------
if before > tris:
    ratio = tris / before
    for m in meshes:
        d = m.modifiers.new("dec", "DECIMATE"); d.ratio = ratio
        bpy.context.view_layer.objects.active = m
        bpy.ops.object.modifier_apply(modifier=d.name)
after = 0
for m in meshes:
    m.data.calc_loop_triangles(); after += len(m.data.loop_triangles)
print(f"[cond] tris {before} -> {after} (budget {tris})")

bpy.ops.export_scene.gltf(filepath=dst, export_format="GLB",
                          export_apply=True, export_yup=True)
print("[cond] exported")
'''


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("src")
    ap.add_argument("dst")
    ap.add_argument("--tris", type=int, default=15000)
    ap.add_argument("--size-mm", type=float, default=0.0,
                    help="real-world length of the longest axis; 0 leaves scale alone")
    ap.add_argument("--mat-class", default="",
                    help="one of: " + ", ".join(sorted(DIELECTRIC | METAL)))
    a = ap.parse_args()

    if not os.path.exists(a.src):
        print(f"FAIL: no such file: {a.src}")
        return 1
    src_bytes = os.path.getsize(a.src)

    script = os.path.join(os.path.dirname(os.path.abspath(__file__)), "_cond.py")
    with open(script, "w", encoding="utf-8") as f:
        f.write(BL)
    raw = a.dst.replace(".glb", ".raw.glb")
    r = subprocess.run(
        [BLENDER, "-b", "--python", script, "--",
         a.src, raw.replace("\\", "/"), str(a.tris), str(a.size_mm), a.mat_class],
        capture_output=True, text=True, errors="replace")
    os.remove(script)
    for line in r.stdout.splitlines():
        if line.startswith("[cond]"):
            print(line)
    if r.returncode != 0 or not os.path.exists(raw):
        print(f"FAIL: blender stage failed (exit {r.returncode})")
        print((r.stderr or r.stdout)[-500:])
        return 1

    # --- two outputs, because they have two different consumers ------------
    # Meshopt lands in extensionsRequired, and Blender's importer cannot read
    # it - so a meshopt file can never go back into the scene. Keep the plain
    # GLB for assembly and emit a separate compressed one for shipping.
    shutil.move(raw, a.dst)
    print(f"[cond] blender asset -> {os.path.basename(a.dst)}")

    web = a.dst.replace(".glb", ".web.glb")
    gt = shutil.which("gltf-transform")
    if not gt:
        print("!! gltf-transform not installed (npm i -g @gltf-transform/cli)"
              " - no web asset written")
    else:
        # prune-attributes false: `optimize` drops UVs it considers unused, and
        # a prop that has no texture YET still needs them for the bake later.
        has_ktx = shutil.which("ktx") is not None
        cmd = [gt, "optimize", a.dst, web,
               "--compress", "meshopt",
               "--prune-attributes", "false",
               "--texture-compress", "ktx2" if has_ktx else "false"]
        pr = subprocess.run(cmd, capture_output=True, text=True, errors="replace")
        if pr.returncode != 0 or not os.path.exists(web):
            print("!! gltf-transform failed; no web asset written")
            print((pr.stderr or pr.stdout)[-400:])
        else:
            note = " + KTX2" if has_ktx else (
                "; textures uncompressed - install KTX-Software for KTX2: "
                "https://github.com/KhronosGroup/KTX-Software/releases")
            print(f"[cond] web asset -> {os.path.basename(web)} (meshopt{note})")
            print(f"[cond] payload {src_bytes/1e6:.2f} MB source -> "
                  f"{os.path.getsize(a.dst)/1e6:.2f} MB blender -> "
                  f"{os.path.getsize(web)/1e6:.2f} MB web")
    print("conditioning passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
