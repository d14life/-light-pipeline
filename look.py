#!/usr/bin/env python
"""
look.py - turn anything into one PNG an agent can actually look at.

The failure this exists to prevent: a model generates an asset, never views it,
and reports "done". Images are the only thing an agent sees natively; a GLB, a
.blend and an .mp4 are opaque blobs. This renders each of them down to a single
contact sheet, so checking a result costs one file read instead of a guess.

    python look.py img   hero.png
    python look.py video plate.mp4 [frames]
    python look.py glb   fan.glb   [views]
    python look.py blend light.blend

Every mode prints `LOOK: <path>` as its last line. Read that file. If a mode
cannot produce a sheet it says so and exits non-zero - silence is never success.
"""

import os
import re
import subprocess
import sys
import tempfile

from PIL import Image, ImageDraw

OUT_DIR = os.path.join(tempfile.gettempdir(), "look")
os.makedirs(OUT_DIR, exist_ok=True)

BLENDER = os.environ.get(
    "BLENDER", r"C:\Program Files\Blender Foundation\Blender 4.5\blender.exe"
)
if not os.path.exists(BLENDER):
    BLENDER = "blender"          # on the pod it is on PATH


def _ffmpeg():
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        return "ffmpeg"


def sheet(paths, out, cols=3, cell=420, labels=None):
    """Tile images into one sheet. Labels are burned in so views stay identifiable."""
    imgs = [Image.open(p).convert("RGB") for p in paths if os.path.exists(p)]
    if not imgs:
        print("!! nothing rendered - no sheet written")
        return None
    cols = min(cols, len(imgs))
    rows = (len(imgs) + cols - 1) // cols
    sh = Image.new("RGB", (cols * cell, rows * cell), (26, 26, 28))
    d = ImageDraw.Draw(sh)
    for i, im in enumerate(imgs):
        im.thumbnail((cell, cell))
        x, y = (i % cols) * cell, (i // cols) * cell
        sh.paste(im, (x + (cell - im.width) // 2, y + (cell - im.height) // 2))
        if labels and i < len(labels):
            d.text((x + 8, y + 6), labels[i], fill=(150, 240, 255))
    sh.save(out)
    return out


def do_img(path):
    im = Image.open(path)
    print(f"[img] {im.size[0]}x{im.size[1]} {im.mode} {os.path.getsize(path)/1e6:.2f} MB")
    if im.mode == "RGBA":
        alpha = im.getchannel("A")
        lo, hi = alpha.getextrema()
        print(f"[img] alpha range {lo}-{hi}" + ("  (fully opaque)" if lo == 255 else ""))
    print(f"LOOK: {path}")
    return path


def do_video(path, n=6):
    """Evenly spaced frames. One still tells you nothing about a 15-second loop."""
    ff = _ffmpeg()
    probe = subprocess.run(
        [ff, "-i", path], capture_output=True, text=True, errors="replace"
    ).stderr
    dur = 0.0
    for line in probe.splitlines():
        if "Duration:" in line:
            h, m, s = line.split("Duration:")[1].split(",")[0].strip().split(":")
            dur = int(h) * 3600 + int(m) * 60 + float(s)
        if "Video:" in line:
            print("[video]", line.strip()[:120])
    print(f"[video] duration {dur:.2f}s, sampling {n} frames")
    frames, labels = [], []
    for i in range(n):
        t = dur * (i + 0.5) / n
        f = os.path.join(OUT_DIR, f"f{i}.png")
        subprocess.run(
            [ff, "-y", "-ss", str(t), "-i", path, "-frames:v", "1", f],
            capture_output=True,
        )
        if os.path.exists(f):
            frames.append(f)
            labels.append(f"{t:.1f}s")
    out = sheet(frames, os.path.join(OUT_DIR, "video_sheet.png"), labels=labels)
    if not out:
        sys.exit(1)
    print(f"LOOK: {out}")
    return out


BL_SCRIPT = r'''
import math, sys, bpy
argv = sys.argv[sys.argv.index("--")+1:]
mode, src, out_dir, views = argv[0], argv[1], argv[2], int(argv[3])

s = bpy.context.scene
s.render.engine = "BLENDER_EEVEE_NEXT"      # a check, not a beauty pass
s.render.resolution_x = s.render.resolution_y = 420
s.render.film_transparent = False
s.view_settings.view_transform = "AgX"

if mode == "glb":
    for o in list(bpy.data.objects):
        bpy.data.objects.remove(o, do_unlink=True)
    bpy.ops.import_scene.gltf(filepath=src)
    meshes = [o for o in bpy.context.scene.objects if o.type == "MESH"]
    if not meshes:
        print("[bl] !! GLB contains no mesh"); sys.exit(3)
    tris = sum(len(m.data.loop_triangles) for m in meshes
               if (m.data.calc_loop_triangles() or True))
    uvs = all(len(m.data.uv_layers) for m in meshes)
    mats = {sl.material.name for m in meshes for sl in m.material_slots if sl.material}
    print(f"[bl] {len(meshes)} mesh, {tris} tris, uv={uvs}, materials={sorted(mats) or 'NONE'}")
    if not uvs:
        print("[bl] !! missing UVs - no albedo/roughness/normal/AO can bind")

    # frame everything, then orbit a camera around it
    import mathutils
    lo = mathutils.Vector(( 1e9,)*3); hi = mathutils.Vector((-1e9,)*3)
    for m in meshes:
        for c in m.bound_box:
            w = m.matrix_world @ mathutils.Vector(c)
            lo = mathutils.Vector(map(min, lo, w)); hi = mathutils.Vector(map(max, hi, w))
    ctr = (lo + hi) / 2; rad = max((hi - lo).length / 2, 1e-3)
    print(f"[bl] bounds {tuple(round(v,3) for v in (hi-lo))}  radius {rad:.3f}")

    world = bpy.data.worlds.new("w"); world.use_nodes = True
    world.node_tree.nodes["Background"].inputs[1].default_value = 1.2
    s.world = world
    key = bpy.data.lights.new("key", "AREA"); key.energy = 400; key.size = rad*4
    ko = bpy.data.objects.new("key", key); s.collection.objects.link(ko)
    ko.location = ctr + mathutils.Vector((rad*2, -rad*2, rad*3))
    ko.rotation_euler = (0.7, 0, 0.8)

    cam = bpy.data.cameras.new("c"); co = bpy.data.objects.new("c", cam)
    s.collection.objects.link(co); s.camera = co
    for i in range(views):
        a = 2*math.pi*i/views
        co.location = ctr + mathutils.Vector(
            (math.cos(a)*rad*3.0, math.sin(a)*rad*3.0, rad*1.4))
        d = ctr - co.location
        co.rotation_euler = d.to_track_quat("-Z", "Y").to_euler()
        s.render.filepath = f"{out_dir}/v{i}.png"
        bpy.ops.render.render(write_still=True)
    print(f"[bl] rendered {views} views")

else:                                        # blend: use the scene's own camera
    bpy.ops.wm.open_mainfile(filepath=src)
    s = bpy.context.scene
    s.render.engine = "BLENDER_EEVEE_NEXT"
    s.render.resolution_x = s.render.resolution_y = 560
    objs = [o.name for o in s.objects]
    print(f"[bl] {len(objs)} objects: {', '.join(sorted(objs)[:14])}")
    for c in bpy.data.collections:
        print(f"[bl] collection {c.name}: {len(c.all_objects)} objects")
    if not s.camera:
        print("[bl] !! no camera in scene - cannot render"); sys.exit(4)
    s.render.filepath = f"{out_dir}/v0.png"
    bpy.ops.render.render(write_still=True)
    print("[bl] rendered scene camera")
'''


def do_blender(mode, src, views=6):
    script = os.path.join(OUT_DIR, "_bl.py")
    with open(script, "w", encoding="utf-8") as f:
        f.write(BL_SCRIPT)
    # Only the numbered view frames - a blanket "v*.png" also ate video_sheet.png.
    for old in os.listdir(OUT_DIR):
        if re.fullmatch(r"v\d+\.png", old):
            os.remove(os.path.join(OUT_DIR, old))
    r = subprocess.run(
        [BLENDER, "-b", "--python", script, "--", mode, src, OUT_DIR.replace("\\", "/"), str(views)],
        capture_output=True, text=True, errors="replace",
    )
    for line in r.stdout.splitlines():
        if line.startswith("[bl]"):
            print(line)
    if r.returncode != 0:
        print(f"!! blender exited {r.returncode}")
        print((r.stderr or r.stdout)[-600:])
        sys.exit(1)
    imgs = sorted(
        (os.path.join(OUT_DIR, f) for f in os.listdir(OUT_DIR)
         if re.fullmatch(r"v\d+\.png", f)),
        key=lambda p: int(os.path.basename(p)[1:-4]),
    )
    labels = [f"{360*i//max(len(imgs),1)}deg" for i in range(len(imgs))] if mode == "glb" else None
    out = sheet(imgs, os.path.join(OUT_DIR, f"{mode}_sheet.png"), labels=labels)
    if not out:
        sys.exit(1)
    print(f"LOOK: {out}")
    return out


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print(__doc__)
        sys.exit(2)
    mode, target = sys.argv[1], sys.argv[2]
    extra = int(sys.argv[3]) if len(sys.argv) > 3 else None
    if not os.path.exists(target):
        print(f"!! no such file: {target}")
        sys.exit(1)
    if mode == "img":
        do_img(target)
    elif mode == "video":
        do_video(target, extra or 6)
    elif mode == "glb":
        do_blender("glb", target, extra or 6)
    elif mode == "blend":
        do_blender("blend", target)
    else:
        print(__doc__)
        sys.exit(2)
