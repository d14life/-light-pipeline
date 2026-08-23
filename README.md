# LIGHT pipeline

Image / video / 3D-model generation on a rented GPU, scene assembly and
web export on the local machine. Claude Code runs on the PC and reaches the
pod over SSH - it is deliberately not installed on the pod, so it can see
local files and the pod at the same time.

## Split

| stage | where | cost |
|---|---|---|
| generate props, images, video | pod, ComfyUI | GPU hours |
| assemble scene, light, materials | PC, Blender + HIP | free |
| final Cycles render | pod (fast) or PC (overnight) | either |
| web conditioning, lens page | PC | free |

## Pod, first run

    # 1. rent: L40S 48 GB, network volume 250 GB -> /workspace, ComfyUI template
    # 2. copy this repo to /workspace
    # 3. accept THREE HF licences, then:
    hf auth login
    bash bootstrap.sh          # ~40-60 min, resumable - rerun if it dies

Gated repos - `facebook/dinov3-...` is reviewed by hand, request it a day early:

  * black-forest-labs/FLUX.2-dev              instant
  * briaai/RMBG-2.0                           instant
  * facebook/dinov3-vitl16-pretrain-lvd1689m  MANUAL

After the nodes install, run Pixal3D's **Environment Check** node before
trusting anything: it names the CUDA wheels that still need building.

## Every run after that

    ssh -L 3000:localhost:3000 root@<pod> -p <port>

The tunnel makes the pod's ComfyUI answer on 127.0.0.1:3000, which is where
`.mcp.json` points. Stop the pod when idle; the volume keeps the weights.

## Local

Blender 4.5.3 LTS, Cycles on HIP (RX 6650 XT), BlenderMCP addon enabled.
Start the socket from the Blender sidebar: View3D > N > BlenderMCP > Start.

    blender -b blender_light_scene.py -- --build --out ./light-local/light.blend

Pod Blender is pinned to the same 4.5.3 so a .blend opens on both ends.
