#!/usr/bin/env python
"""
Put the reference photograph back onto the mesh.

    python conditioning/reproject.py pump.glb ref_pump.png pump_tex.glb

Pixal3D returns solid geometry and a washed-out albedo - a black anodised pump
comes back pale grey, brass comes back grey. The colour is not lost, it is
sitting in the reference image that produced the mesh. This projects that image
back onto the geometry from the camera it was shot from and bakes it into the
existing UVs.

What this can and cannot do, plainly: the projection is correct for the side
the camera saw and invents nothing for the rest, so the back gets the same
pixels smeared along the projection axis. For a prop that faces the camera in
the final shot that is fine and it is a large improvement. For anything the
viewer orbits, generate more views instead - Trellis2's multiview nodes are the
real answer there.
"""

import os
import subprocess
import sys

BLENDER = os.environ.get(
    "BLENDER", r"C:\Program Files\Blender Foundation\Blender 4.5\blender.exe")
if not os.path.exists(BLENDER):
    BLENDER = "blender"

BL = r'''
import sys, bpy, mathutils
argv = sys.argv[sys.argv.index("--")+1:]
src, ref, dst, res = argv[0], argv[1], argv[2], int(argv[3])

for o in list(bpy.data.objects):
    bpy.data.objects.remove(o, do_unlink=True)
bpy.ops.import_scene.gltf(filepath=src)
meshes = [o for o in bpy.context.scene.objects if o.type == "MESH"]
if not meshes:
    print("[proj] !! no mesh"); sys.exit(3)
obj = meshes[0]
for m in meshes[1:]:
    m.select_set(True)
if len(meshes) > 1:
    bpy.context.view_layer.objects.active = obj
    obj.select_set(True)
    bpy.ops.object.join()
print(f"[proj] mesh {len(obj.data.polygons)} faces, uv={bool(obj.data.uv_layers)}")

if not obj.data.uv_layers:
    bpy.context.view_layer.objects.active = obj
    bpy.ops.object.mode_set(mode="EDIT"); bpy.ops.mesh.select_all(action="SELECT")
    bpy.ops.uv.smart_project(angle_limit=1.15, island_margin=0.02)
    bpy.ops.object.mode_set(mode="OBJECT")
    print("[proj] unwrapped")

# --- camera, framed exactly the way the reference was ------------------------
# The generated shot is a centred product view, so a camera pointed at the
# bounding-box centre from +Y reproduces it closely enough to project.
lo = mathutils.Vector((1e9,)*3); hi = mathutils.Vector((-1e9,)*3)
for c in obj.bound_box:
    w = obj.matrix_world @ mathutils.Vector(c)
    lo = mathutils.Vector(map(min, lo, w)); hi = mathutils.Vector(map(max, hi, w))
ctr = (lo + hi) / 2
size = max(hi - lo)

cam_data = bpy.data.cameras.new("proj")
cam_data.type = "ORTHO"
cam_data.ortho_scale = size * 1.02      # the render framed the object tightly
cam = bpy.data.objects.new("proj", cam_data)
bpy.context.scene.collection.objects.link(cam)
cam.location = ctr + mathutils.Vector((0, -size * 3, 0))
cam.rotation_euler = (1.5708, 0, 0)
bpy.context.scene.camera = cam

# --- material: the reference, addressed in camera space ----------------------
mat = bpy.data.materials.new("projected")
mat.use_nodes = True
nt = mat.node_tree
for n in list(nt.nodes):
    nt.nodes.remove(n)
out = nt.nodes.new("ShaderNodeOutputMaterial")
emit = nt.nodes.new("ShaderNodeEmission")          # emission bakes 1:1, no light
tex = nt.nodes.new("ShaderNodeTexImage")
tex.image = bpy.data.images.load(ref)
tex.extension = "EXTEND"
coord = nt.nodes.new("ShaderNodeTexCoord")
coord.object = cam
nt.links.new(coord.outputs["Window"], tex.inputs["Vector"])
nt.links.new(tex.outputs["Color"], emit.inputs["Color"])
nt.links.new(emit.outputs["Emission"], out.inputs["Surface"])
obj.data.materials.clear()
obj.data.materials.append(mat)

# --- bake it into the UVs ----------------------------------------------------
baked = bpy.data.images.new("baked", res, res)
bake_node = nt.nodes.new("ShaderNodeTexImage")
bake_node.image = baked
nt.nodes.active = bake_node

s = bpy.context.scene
s.render.engine = "CYCLES"
s.cycles.device = "GPU"
s.cycles.samples = 4                    # emission is flat; more samples buy nothing
s.render.bake.use_selected_to_active = False
s.render.bake.margin = 8
bpy.context.view_layer.objects.active = obj
obj.select_set(True)
bpy.ops.object.bake(type="EMIT")
print("[proj] baked")

# --- rebuild as a real surface, not an emitter -------------------------------
for n in list(nt.nodes):
    nt.nodes.remove(n)
out = nt.nodes.new("ShaderNodeOutputMaterial")
bsdf = nt.nodes.new("ShaderNodeBsdfPrincipled")
img = nt.nodes.new("ShaderNodeTexImage")
img.image = baked
nt.links.new(img.outputs["Color"], bsdf.inputs["Base Color"])
nt.links.new(bsdf.outputs["BSDF"], out.inputs["Surface"])
bsdf.inputs["Roughness"].default_value = 0.45
bsdf.inputs["Metallic"].default_value = 0.0

bpy.ops.export_scene.gltf(filepath=dst, export_format="GLB", export_apply=True)
print("[proj] exported " + dst)
'''


def main():
    if len(sys.argv) < 4:
        print(__doc__)
        return 2
    src, ref, dst = sys.argv[1], sys.argv[2], sys.argv[3]
    res = int(sys.argv[4]) if len(sys.argv) > 4 else 2048
    for p in (src, ref):
        if not os.path.exists(p):
            print("FAIL: missing " + p)
            return 1

    script = os.path.join(os.path.dirname(os.path.abspath(__file__)), "_proj.py")
    with open(script, "w", encoding="utf-8") as f:
        f.write(BL)
    r = subprocess.run([BLENDER, "-b", "--python", script, "--",
                        src.replace("\\", "/"), ref.replace("\\", "/"),
                        dst.replace("\\", "/"), str(res)],
                       capture_output=True, text=True, errors="replace")
    os.remove(script)
    for line in r.stdout.splitlines():
        if line.startswith("[proj]"):
            print(line)
    if r.returncode != 0 or not os.path.exists(dst):
        print("FAIL: blender exited %d" % r.returncode)
        print((r.stderr or r.stdout)[-600:])
        return 1
    print("reprojection passed (%.2f MB)" % (os.path.getsize(dst) / 1e6))
    return 0


if __name__ == "__main__":
    sys.exit(main())
