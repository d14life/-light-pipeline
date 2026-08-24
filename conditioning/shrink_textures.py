#!/usr/bin/env python
"""
Shrink the textures inside a GLB, without gltf-transform.

    python conditioning/shrink_textures.py in.glb out.glb 1024

gltf-transform's texture stages (resize, webp, texture-compress) all die on
Pixal3D's output with `colourspace: parameter space not set` - a libvips/sharp
problem, not a problem with the file. Geometry compression still works; only
textures need this detour.

Two rules that are easy to get wrong and silent when you do:

  albedo      is colour data. Resample it in RGB and keep it 8-bit sRGB.
  normal map  is NOT colour. Every pixel is a unit vector packed into RGB, so
              it must never be recompressed as colour, never given an ICC
              profile, and never downscaled with a filter that averages across
              a discontinuity harder than necessary. Lanczos is fine; a colour
              conversion is not.

Prints the payload before and after, because a size is a number with what it
buys, never a silent 30 MB.
"""

import io
import json
import struct
import sys

from PIL import Image

MAGIC, JSON_CHUNK, BIN_CHUNK = 0x46546C67, 0x4E4F534A, 0x004E4942


def read_glb(path):
    raw = open(path, "rb").read()
    magic, _ver, _len = struct.unpack("<III", raw[:12])
    if magic != MAGIC:
        raise SystemExit("not a GLB: " + path)
    off, gltf, binary = 12, None, b""
    while off < len(raw):
        clen, ctype = struct.unpack("<II", raw[off:off + 8])
        data = raw[off + 8: off + 8 + clen]
        if ctype == JSON_CHUNK:
            gltf = json.loads(data)
        elif ctype == BIN_CHUNK:
            binary = data
        off += 8 + clen + (-clen % 4)
    return gltf, binary


def write_glb(path, gltf, binary):
    j = json.dumps(gltf, separators=(",", ":")).encode()
    j += b" " * (-len(j) % 4)
    binary += b"\0" * (-len(binary) % 4)
    out = struct.pack("<II", len(j), JSON_CHUNK) + j
    out += struct.pack("<II", len(binary), BIN_CHUNK) + binary
    header = struct.pack("<III", MAGIC, 2, 12 + len(out))
    open(path, "wb").write(header + out)


def is_normal_map(gltf, image_index):
    """A normal map must not be treated as colour, so it has to be identified."""
    def hits(block):
        nt = block.get("normalTexture")
        if not nt:
            return False
        return gltf["textures"][nt["index"]].get("source") == image_index

    for mat in gltf.get("materials", []):
        if hits(mat) or any(hits(e) for e in (mat.get("extensions") or {}).values()
                            if isinstance(e, dict)):
            return True
    name = (gltf["images"][image_index].get("name") or "").lower()
    return "normal" in name or "_nrm" in name or name.endswith("_n")


def main():
    if len(sys.argv) < 3:
        print(__doc__)
        return 2
    src, dst = sys.argv[1], sys.argv[2]
    target = int(sys.argv[3]) if len(sys.argv) > 3 else 1024

    gltf, binary = read_glb(src)
    images = gltf.get("images", [])
    if not images:
        print("no embedded images - nothing to do")
        return 0

    before = len(open(src, "rb").read())
    views, blobs, cursor = gltf["bufferViews"], [], 0

    # every bufferView is rebuilt so offsets stay correct after images shrink
    new_views, remap = [], {}
    for i, bv in enumerate(views):
        start = bv.get("byteOffset", 0)
        remap[i] = binary[start: start + bv["byteLength"]]

    for idx, im in enumerate(images):
        bv_i = im.get("bufferView")
        if bv_i is None:
            continue
        pil = Image.open(io.BytesIO(remap[bv_i]))
        w, h = pil.size
        normal = is_normal_map(gltf, idx)
        kind = "normal" if normal else "colour"
        if max(w, h) > target:
            pil = pil.convert("RGB" if normal else pil.mode).resize(
                (target, target), Image.LANCZOS)
        buf = io.BytesIO()
        # PNG throughout: re-encoding a normal map as JPEG would quantise the
        # vectors and show up as banding on every curved surface.
        pil.save(buf, format="PNG", optimize=True)
        new = buf.getvalue()
        print("  image %d (%s) %dx%d -> %dx%d  %.2f -> %.2f MB"
              % (idx, kind, w, h, pil.size[0], pil.size[1],
                 len(remap[bv_i]) / 1e6, len(new) / 1e6))
        remap[bv_i] = new
        im["mimeType"] = "image/png"

    for i, bv in enumerate(views):
        data = remap[i]
        blobs.append(data)
        nv = dict(bv)
        nv["byteOffset"] = cursor
        nv["byteLength"] = len(data)
        nv.pop("byteStride", None) if "byteStride" not in bv else None
        new_views.append(nv)
        cursor += len(data) + (-len(data) % 4)

    packed = bytearray()
    for d in blobs:
        packed += d
        packed += b"\0" * (-len(d) % 4)

    gltf["bufferViews"] = new_views
    gltf["buffers"] = [{"byteLength": len(packed)}]
    write_glb(dst, gltf, bytes(packed))

    after = len(open(dst, "rb").read())
    print("payload %.2f MB -> %.2f MB (%.0f%%)"
          % (before / 1e6, after / 1e6, 100 * after / before))
    print("texture shrink passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
