# Working rules for this repo

## 1. Look at it. Every time. No exceptions.

**Never report a generated artifact as done without having viewed it in this
session.** Not "the code that makes it is present", not "it ran without errors",
not "the file exists and is 4 MB". Those are not evidence. The image is.

This rule exists because it was broken repeatedly and shipped bad results:
generations came back wrong in ways obvious to any human glancing at them, and
were handed over as finished because nobody looked.

    python look.py img   hero.png          # dimensions, alpha, then the image
    python look.py video plate.mp4 8       # 8 evenly spaced frames, one sheet
    python look.py glb   fan.glb 6         # tris, UVs, materials + 6 orbit views
    python look.py blend light.blend       # object tree + scene camera render

Each prints `LOOK: <path>` last. **Read that file.** If a mode cannot produce a
sheet it exits non-zero and says why — silence is never success.

One frame does not verify a 15-second clip. One angle does not verify a mesh:
image-to-3D hallucinates the side the camera never saw, so the back is exactly
where it fails. Sample across time and around the object.

## 2. Show the user at every step

Send the artifact with `SendUserFile`, do not describe it. They spot in one
second what takes paragraphs to explain, and they are the one who knows what it
was supposed to look like. A step is not complete until they have seen it.

## 3. Ask before spending

If the intent is ambiguous, **ask** — do not pick the reading that lets you
start working. A wrong assumption costs a GPU hour and a rebuild; a question
costs one message. Specifically, ask when:

* the target design is unclear (there is more than one visual direction on disk)
* a choice changes what gets generated, not just how
* a step would overwrite or discard existing work
* the cost is about to jump — a long render, a big download, a paid API call

## 4. What counts as verified

| claim | evidence required |
|---|---|
| "the mesh is good" | orbit sheet viewed; tris, UVs, materials reported |
| "the video works" | frame sheet across the full duration, viewed |
| "the render is right" | the PNG, viewed, at 1:1 for detail claims |
| "the page works" | screenshot or DOM read, not "the server returned 200" |
| "the script runs" | it ran, and its output was read |

For a photoreal target, add the brief's own test: put it beside a real
photograph. If someone picks the render in two seconds, it is not done.

## 5. Report honestly

If a step failed, say so with the output. If a step was skipped, say that. If
something was verified only partially — "renders on my GPU, untested on the
pod" — say exactly that. Never round a partial result up to a finished one.
