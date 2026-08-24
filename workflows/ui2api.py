#!/usr/bin/env python
"""
Convert a ComfyUI UI-format workflow into the API format /prompt accepts.

    python workflows/ui2api.py MeshWithTexturing_MultiView.json out.json

Every node pack ships its workflows in the editor's own format - nodes with a
separate `links` table - while the API wants each input resolved inline as
[node_id, slot]. That one difference is why shipped example graphs cannot be
posted directly, and why it is tempting to hand-write a graph instead and get
the wiring subtly wrong. Converting is thirty lines and inherits the pack
author's wiring exactly.

Widget values are positional in the UI format: a node's widgets_values list
lines up with its non-link inputs in the order the node declares them, so the
mapping needs the live /object_info to name them.
"""

import json
import sys
import urllib.request

API = "http://127.0.0.1:3000"


def object_info():
    with urllib.request.urlopen(API + "/object_info", timeout=60) as r:
        return json.load(r)


def convert(ui, info):
    # link id -> (source node id, source slot)
    src = {}
    for l in ui.get("links", []):
        # [link_id, from_node, from_slot, to_node, to_slot, type]
        src[l[0]] = (str(l[1]), l[2])

    out = {}
    skipped = []
    for n in ui["nodes"]:
        t = n.get("type")
        if t in ("Note", "MarkdownNote", "Reroute", "PrimitiveNode"):
            skipped.append(t)
            continue
        if t not in info:
            skipped.append(t + " (not installed)")
            continue

        spec = info[t]["input"]
        # widget inputs are the required/optional entries that are not links
        linked = {i.get("name") for i in (n.get("inputs") or []) if i.get("link") is not None}
        widget_names = []
        for grp in ("required", "optional"):
            for k, v in (spec.get(grp) or {}).items():
                if k in linked:
                    continue
                # a slot whose type is a list of choices or a primitive is a widget
                if isinstance(v[0], list) or v[0] in ("INT", "FLOAT", "STRING", "BOOLEAN", "COMBO"):
                    widget_names.append(k)

        inputs = {}
        vals = list(n.get("widgets_values") or [])
        for i, k in enumerate(widget_names):
            if i < len(vals):
                inputs[k] = vals[i]
        for slot in (n.get("inputs") or []):
            if slot.get("link") is not None and slot["link"] in src:
                inputs[slot["name"]] = list(src[slot["link"]])

        out[str(n["id"])] = {"class_type": t, "inputs": inputs}

    # drop links that point at nodes we skipped, or /prompt rejects the graph
    for node in out.values():
        for k, v in list(node["inputs"].items()):
            if isinstance(v, list) and len(v) == 2 and str(v[0]) not in out:
                del node["inputs"][k]

    return out, skipped


def main():
    if len(sys.argv) < 3:
        print(__doc__)
        return 2
    ui = json.load(open(sys.argv[1], encoding="utf-8"))
    api, skipped = convert(ui, object_info())
    json.dump(api, open(sys.argv[2], "w", encoding="utf-8"), indent=1)
    print("converted %d nodes -> %s" % (len(api), sys.argv[2]))
    if skipped:
        print("skipped: " + ", ".join(sorted(set(skipped))))
    for nid, n in api.items():
        if n["class_type"].startswith("Trellis2LoadImage"):
            print("  image input: node %s -> %s" % (nid, n["inputs"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
