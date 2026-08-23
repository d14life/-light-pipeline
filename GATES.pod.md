# Gates: pod bring-up

Scope: prove the pod is genuinely usable after bootstrap.sh, before any
generation is attempted. Not discovered by the Stop hook - `GATES.md` and
`gates/*.md` are, this is not. Activate it on the pod with:

    cp GATES.pod.md GATES.md
    node ~/.claude/skills/unlazy/scripts/gate-check.mjs --status GATES.md
    node ~/.claude/skills/unlazy/scripts/gate-check.mjs --approve GATES.md

Every gate here guards a failure that is silent. A download can land where
ComfyUI never looks; a gated repo can be skipped while everything around it
succeeds; Cycles can fall back to CPU and merely be slow.

- [ ] P1: Blender is installed, matches the PC's 4.5 LTS, and has a GPU backend
  CHECK: python checks/verify_pod.py blender
  EXPECT: blender verification passed
  EVIDENCE: pending

- [ ] P2: all four ComfyUI custom nodes are cloned and non-empty
  CHECK: python checks/verify_pod.py nodes
  EXPECT: custom node verification passed
  EVIDENCE: pending

- [ ] P3: the big checkpoints exist at a sane size, not as gated-repo stubs
  CHECK: python checks/verify_pod.py weights
  EXPECT: weight verification passed
  EVIDENCE: pending

- [ ] P4: weights sit in folders ComfyUI scans, not under models/split_files
  CHECK: python checks/verify_pod.py layout
  EXPECT: layout verification passed
  EVIDENCE: pending

- [ ] P5: ComfyUI answers on its API and can actually see the flux2 checkpoint
  CHECK: python checks/verify_pod.py comfy-api
  EXPECT: comfy api verification passed
  EVIDENCE: pending

- [ ] P6: Pixal3D's CUDA kernels and FlashAttention import for real
  CHECK: python checks/verify_pod.py pixal-wheels
  EXPECT: pixal wheel verification passed
  EVIDENCE: pending
