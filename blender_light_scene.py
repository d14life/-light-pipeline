"""
LIGHT - scene scaffold.

Run inside Blender:  blender -b --python blender_light_scene.py -- --build

This file is the answer to "how does the model know which block is what".
Nothing here is clever: an object is legible to an agent because of its NAME,
the COLLECTION it sits in, and the CUSTOM PROPERTIES bolted to it. Claude reads
the scene graph over MCP and sees exactly those three things - so an object
called `Cube.017` is invisible to it, and `H_fan_120` is addressable.

The two-layer render at the bottom is the whole reason for doing this on a
server rather than in Higgsfield: both layers come out of ONE scene through
ONE camera, so they register pixel-for-pixel by construction. The matched-set
README notes the AI pair drifted because "the model repainted the panel between
them". That failure cannot happen here.
"""

import os
import sys

import bpy
from mathutils import Vector

WORD = "LIGHT"

# Every part that goes inside a letter. `ref` points at the crop it was
# generated from, so the provenance survives into the .blend and an agent can
# be told "rebuild everything that came from img_059".
KIT = {
    "L": [("cpu",          "img_057"), ("board",   "img_057"),
          ("gear_cluster", "img_057"), ("tube",    "img_057")],
    "I": [("ram_01",       "img_058"), ("ram_02",  "img_058"),
          ("ram_03",       "img_058"), ("tube",    "img_058")],
    "G": [("heatsink",     "img_060"), ("board",   "img_060"),
          ("tube",         "img_060")],
    "H": [("coolant_main", "img_059"), ("pump",    "img_059"),
          ("fan_120",      "img_059"), ("battery", "img_059"),
          ("tube",         "img_059")],
    "T": [("chain_drive",  "img_061"), ("sprocket_top", "img_061"),
          ("sprocket_bot", "img_061"), ("board",  "img_061"),
          ("tube",         "img_061")],
}

# What each part is made of. Generative PBR guesses this wrong - a moulded part
# comes back at metalness 0.7 and reads as painted metal - so the class is
# declared here and applied over whatever the generator produced.
MAT_CLASS = {
    "cpu": "ceramic", "board": "pcb", "gear_cluster": "steel",
    "ram_01": "pcb", "ram_02": "pcb", "ram_03": "pcb",
    "heatsink": "aluminium", "coolant_main": "glass_fluid",
    "pump": "steel", "fan_120": "plastic", "battery": "steel",
    "chain_drive": "steel", "sprocket_top": "steel", "sprocket_bot": "steel",
    "tube": "emissive_neon",
}


def col(name, parent=None):
    """Get or make a collection, linked under `parent` (scene root if None)."""
    c = bpy.data.collections.get(name)
    if c is None:
        c = bpy.data.collections.new(name)
        (parent or bpy.context.scene.collection).children.link(c)
    return c


def build_skeleton():
    """
    One collection per letter, each split into shell and guts.

    The split is not cosmetic - it is what the two render passes toggle. Layer 1
    shows shells and hides guts; layer 2 makes shells transparent and shows the
    guts. Because it is a visibility flip on named collections, the camera never
    moves and the two frames line up exactly.
    """
    # Blender opens on Cube/Light/Camera in a collection called "Collection";
    # none of it is part of the asset.
    for o in list(bpy.data.objects):
        bpy.data.objects.remove(o, do_unlink=True)
    startup = bpy.data.collections.get("Collection")
    if startup is not None and not startup.objects and not startup.children:
        bpy.data.collections.remove(startup)

    root = col("LIGHT")
    for letter in dict.fromkeys(WORD):          # dedupe, keep order
        lc = col(f"letter_{letter}", root)
        col(f"{letter}_shell", lc)              # the acrylic / aluminium case
        col(f"{letter}_guts", lc)               # everything inside it
    col("stage", root)                          # board, camera, lights
    print(f"[scaffold] built {len(dict.fromkeys(WORD))} letter collections")


def place(glb_path, letter, part, location, rotation=(0, 0, 0), scale=1.0):
    """
    Import one generated GLB and make it legible.

    Three things happen here and all three are for the agent's benefit:
      name        -> `H_fan_120`, so it can be addressed in a sentence
      collection  -> `H_guts`,    so a render pass can hide it as a group
      properties  -> ref crop + material class, so provenance and surface
                     survive into the file instead of living in a chat log
    """
    before = set(bpy.data.objects)
    bpy.ops.import_scene.gltf(filepath=glb_path)
    imported = [o for o in set(bpy.data.objects) - before]
    if not imported:
        print(f"!! nothing imported from {glb_path}")
        return None

    # A generated GLB usually arrives as several parts; parent them to one empty
    # so the whole thing moves as a unit and carries a single name. Only the
    # ROOTS get reparented - grabbing every object would flatten the GLB's own
    # hierarchy and shift children whose transforms were relative to a parent.
    roots = [o for o in imported if o.parent is None or o.parent not in imported]
    if len(roots) == 1:
        obj = roots[0]
    else:
        obj = bpy.data.objects.new(f"{letter}_{part}", None)
        bpy.context.scene.collection.objects.link(obj)
        for r in roots:
            r.parent = obj

    obj.name = f"{letter}_{part}"
    obj.location = Vector(location)
    obj.rotation_euler = rotation
    obj.scale = (scale, scale, scale)

    obj["letter"] = letter
    obj["part"] = part
    obj["mat_class"] = MAT_CLASS.get(part, "unknown")

    target = col(f"{letter}_guts")
    for c in list(obj.users_collection):
        c.objects.unlink(obj)
    target.objects.link(obj)
    for child in imported:
        if child is not obj:
            for c in list(child.users_collection):
                c.objects.unlink(child)
            target.objects.link(child)

    print(f"[place] {obj.name}  <- {glb_path}  ({obj['mat_class']})")
    return obj


def set_visibility(layer):
    """
    layer 1 - the shell:  cases solid, guts hidden.
    layer 2 - the works:  cases transparent, guts shown.

    Six lines. This is the entire mechanism behind pixel-perfect registration,
    and the reason the pair cannot drift between generations.
    """
    for letter in dict.fromkeys(WORD):
        shell = bpy.data.collections.get(f"{letter}_shell")
        guts = bpy.data.collections.get(f"{letter}_guts")
        if shell:
            for o in shell.all_objects:
                o.hide_render = False
                # the shell material carries both looks; the agent flips this
                o["look"] = "aluminium" if layer == 1 else "acrylic"
        if guts:
            for o in guts.all_objects:
                o.hide_render = (layer == 1)


def render_pair(out_dir, frames=1):
    """Both layers, one camera, no repositioning between them."""
    scene = bpy.context.scene
    scene.render.engine = "CYCLES"
    scene.cycles.device = "GPU"
    scene.view_settings.view_transform = "AgX"     # applied exactly once
    scene.render.film_transparent = False

    for layer in (1, 2):
        set_visibility(layer)
        name = "plate" if layer == 1 else "xray"
        scene.render.filepath = f"{out_dir}/{name}_"
        if frames > 1:
            scene.frame_start, scene.frame_end = 1, frames
            bpy.ops.render.render(animation=True)
        else:
            bpy.ops.render.render(write_still=True)
        print(f"[render] layer {layer} -> {out_dir}/{name}_")


def describe():
    """
    What an agent sees when it reads this scene.

    Prints empty collections too - at scaffold time an empty `H_guts` is the
    thing you are checking for, and hiding it would hide the whole point.
    """
    def walk(c, depth=0):
        objs = sorted(o.name for o in c.objects)
        tail = "  " + ", ".join(objs) if objs else "  (empty)"
        print(f"[tree] {'  ' * depth}{c.name}{tail}")
        for child in sorted(c.children, key=lambda x: x.name):
            walk(child, depth + 1)

    for c in bpy.context.scene.collection.children:
        walk(c)
    loose = [o.name for o in bpy.context.scene.collection.objects]
    if loose:
        print(f"[tree] (scene root)  {', '.join(sorted(loose))}")


if __name__ == "__main__":
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    if "--build" in argv:
        # --out lets the same file run on Windows locally and on the pod.
        out = "/workspace/light/light.blend"
        if "--out" in argv:
            out = argv[argv.index("--out") + 1]
        build_skeleton()
        describe()
        os.makedirs(os.path.dirname(out), exist_ok=True)
        bpy.ops.wm.save_as_mainfile(filepath=out)
        print(f"[scaffold] saved {out}")
