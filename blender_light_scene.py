"""
LIGHT - scene scaffold.

    blender -b --python blender_light_scene.py -- --build --out ./light.blend

What is actually being built, read off ASSEMBLED_XRAY_REF.png and PLATE_ON.png:
a watercooled machine in an aluminium case, where the coolant reservoir is
shaped like the word LIGHT. The word is milled through the white front panel,
and lit coolant glows out through the aperture.

  layer 1 "plate"  panel opaque white; the word glows through the cut-out;
                   board and loop are hidden (the panel occludes them anyway,
                   hiding just saves the render time)
  layer 2 "xray"   panel transparent; board, reservoir letters and tubing all
                   visible - the same case, seen through

Both layers come out of ONE scene through ONE camera, so they register
pixel-for-pixel. The matched-set README records the AI pair drifting because
"the model repainted the panel between them"; that cannot happen here.

This file is also the answer to "how does the model know which block is what".
An object is legible to an agent through its NAME, its COLLECTION, and its
CUSTOM PROPERTIES. `Cube.017` is invisible to reasoning; `mb_fan_left` in
`board` with mat_class `plastic` can be addressed in a sentence.
"""

import os
import sys

import bpy
from mathutils import Vector

WORD = "LIGHT"

# ---------------------------------------------------------------- parts list
# Read off the reference, not invented. `ref` keeps provenance in the .blend so
# an agent can be told "regenerate everything that came from the xray ref".
PARTS = {
    "case": [
        ("case_frame",   "brushed aluminium, chamfered, rounded corners"),
        ("case_panel",   "white front panel, WORD milled through it"),
        ("case_vent",    "grille along the bottom edge"),
        ("case_feet",    "two feet"),
        ("case_bolts",   "four corner bolts"),
    ],
    # The letters ARE the reservoir - clear acrylic channel blocks with screw
    # rows along the edge and a port at each end. Not shells full of hardware.
    "word": [(f"res_{c}", "acrylic reservoir channel") for c in dict.fromkeys(WORD)],
    "board": [
        ("mb_pcb",       "backplane, dark green, traces"),
        ("mb_cpu",       "large die with visible gold bond wires"),
        ("mb_ram",       "DIMM slots"),
        ("mb_fan_left",  "80mm case fan"),
        ("mb_gpu",       "expansion card"),
        ("mb_gpu_fan",   "blower on the card"),
        ("mb_radiator",  "copper finned block, bottom centre"),
        ("mb_cylinder",  "upright cylindrical reservoir / capacitor"),
        ("mb_modules",   "flat dark modules, bottom corners"),
    ],
    "loop": [
        ("pump",         "pump and valve body, bottom left"),
        ("tube_main",    "maroon soft tube, the long run"),
        ("tube_return",  "maroon soft tube, return leg"),
        ("tube_aux",     "green/teal tube, left side"),
        ("fittings",     "compression collars at every junction"),
    ],
}

# Generative PBR guesses material class wrong - a moulded part comes back near
# metalness 0.7 and reads as painted metal. Declared here, applied over it.
MAT_CLASS = {
    "case_frame": "aluminium", "case_panel": "white_plastic",
    "case_vent": "aluminium", "case_feet": "rubber", "case_bolts": "steel",
    "mb_pcb": "pcb", "mb_cpu": "ceramic", "mb_ram": "pcb",
    "mb_fan_left": "plastic", "mb_gpu": "pcb", "mb_gpu_fan": "plastic",
    "mb_radiator": "copper", "mb_cylinder": "steel", "mb_modules": "plastic",
    "pump": "steel", "fittings": "steel",
    "tube_main": "rubber", "tube_return": "rubber", "tube_aux": "rubber",
}
for c in dict.fromkeys(WORD):
    MAT_CLASS[f"res_{c}"] = "acrylic_coolant"      # clear shell + lit fluid


def col(name, parent=None):
    c = bpy.data.collections.get(name)
    if c is None:
        c = bpy.data.collections.new(name)
        (parent or bpy.context.scene.collection).children.link(c)
    return c


def build_skeleton():
    """Empty collections plus one named placeholder per part.

    The placeholders are empties, not geometry: they hold the name, the
    collection and the properties, so an agent can reason about and position
    the scene before a single mesh exists. Generated GLBs replace them later.
    """
    for o in list(bpy.data.objects):
        bpy.data.objects.remove(o, do_unlink=True)
    startup = bpy.data.collections.get("Collection")
    if startup is not None and not startup.objects and not startup.children:
        bpy.data.collections.remove(startup)

    root = col("LIGHT")
    for group, parts in PARTS.items():
        gc = col(group, root)
        for name, note in parts:
            e = bpy.data.objects.new(name, None)
            e.empty_display_type = "PLAIN_AXES"
            gc.objects.link(e)
            e["group"] = group
            e["note"] = note
            e["mat_class"] = MAT_CLASS.get(name, "unknown")
            e["placeholder"] = True
    col("stage", root)                      # camera and lights
    n = sum(len(v) for v in PARTS.values())
    print(f"[scaffold] {len(PARTS)} groups, {n} named placeholders")


def place(glb_path, group, part, location, rotation=(0, 0, 0), scale=1.0):
    """Import a generated GLB, name it, file it, tag it - and drop its placeholder."""
    before = set(bpy.data.objects)
    bpy.ops.import_scene.gltf(filepath=glb_path)
    imported = list(set(bpy.data.objects) - before)
    if not imported:
        print(f"!! nothing imported from {glb_path}")
        return None

    # Reparent ROOTS only. Grabbing every object would flatten the GLB's own
    # hierarchy and shift children whose transforms were relative to a parent.
    roots = [o for o in imported if o.parent is None or o.parent not in imported]
    if len(roots) == 1:
        obj = roots[0]
    else:
        obj = bpy.data.objects.new(part, None)
        bpy.context.scene.collection.objects.link(obj)
        for r in roots:
            r.parent = obj

    old = bpy.data.objects.get(part)
    if old is not None and old.get("placeholder"):
        bpy.data.objects.remove(old, do_unlink=True)

    obj.name = part
    obj.location = Vector(location)
    obj.rotation_euler = rotation
    obj.scale = (scale, scale, scale)
    obj["group"] = group
    obj["part"] = part
    obj["mat_class"] = MAT_CLASS.get(part, "unknown")

    target = col(group)
    for o in [obj] + [c for c in imported if c is not obj]:
        for c in list(o.users_collection):
            c.objects.unlink(o)
        target.objects.link(o)

    print(f"[place] {obj.name} <- {os.path.basename(glb_path)} ({obj['mat_class']})")
    return obj


def set_layer(layer):
    """
    1 = plate: panel opaque, word glowing through the cut-out, insides hidden.
    2 = xray:  panel transparent, everything visible.

    A visibility flip on named collections - the camera never moves, so the two
    frames line up exactly. That is the whole reason this runs in Blender.
    """
    hide_inside = (layer == 1)
    for group in ("board", "loop"):
        c = bpy.data.collections.get(group)
        if c:
            for o in c.all_objects:
                o.hide_render = hide_inside
    for group in ("case", "word"):
        c = bpy.data.collections.get(group)
        if c:
            for o in c.all_objects:
                o.hide_render = False
                o["look"] = "opaque" if layer == 1 else "xray"
    print(f"[layer] {layer} ({'plate' if layer == 1 else 'xray'}): "
          f"board+loop hidden={hide_inside}")


def render_pair(out_dir, frames=1):
    s = bpy.context.scene
    s.render.engine = "CYCLES"
    s.cycles.device = "GPU"
    s.view_settings.view_transform = "AgX"      # applied exactly once
    if not s.camera:
        print("[render] !! no camera in scene - nothing rendered")
        return False
    os.makedirs(out_dir, exist_ok=True)
    for layer in (1, 2):
        set_layer(layer)
        s.render.filepath = f"{out_dir}/{'plate' if layer == 1 else 'xray'}_"
        if frames > 1:
            s.frame_start, s.frame_end = 1, frames
            bpy.ops.render.render(animation=True)
        else:
            bpy.ops.render.render(write_still=True)
        print(f"[render] layer {layer} -> {s.render.filepath}")
    return True


def describe():
    """Prints empty collections too - at scaffold time that is the thing to check."""
    def walk(c, depth=0):
        objs = sorted(o.name for o in c.objects)
        print(f"[tree] {'  ' * depth}{c.name}" + ("  " + ", ".join(objs) if objs else "  (empty)"))
        for ch in sorted(c.children, key=lambda x: x.name):
            walk(ch, depth + 1)
    for c in bpy.context.scene.collection.children:
        walk(c)


if __name__ == "__main__":
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    if "--build" in argv:
        out = "/workspace/light/light.blend"
        if "--out" in argv:
            out = argv[argv.index("--out") + 1]
        build_skeleton()
        describe()
        d = os.path.dirname(out)
        if d:
            os.makedirs(d, exist_ok=True)
        bpy.ops.wm.save_as_mainfile(filepath=out)
        print(f"[scaffold] saved {out}")
