#!/usr/bin/env bash
# ============================================================
#  One command, whole pipeline. Target: L40S 48 GB, /workspace on a 250 GB volume.
#
#  Capabilities after this finishes:
#    image     FLUX.2 dev  (32B, fp8mixed)      -> ComfyUI
#    video     Wan 2.2 I2V-A14B (fp16, MoE)     -> ComfyUI
#    3D model  Pixal3D / TRELLIS.2 / Hunyuan3D  -> ComfyUI
#    3D scene  Blender + Cycles, driven by Claude on YOUR machine over SSH
#
#  Claude Code is deliberately NOT installed here. It runs on your PC and
#  reaches this pod through:  ssh -L 3000:localhost:3000 root@<pod> -p <port>
#
#  Put these four files in /workspace and run:
#      bash bootstrap.sh
#
#      bootstrap.sh             this
#      install-server-stack.sh  Blender + Cycles GPU + ComfyUI custom nodes
#      runpod-3d-setup.sh       FLUX.2 + Pixal3D + TRELLIS.2 weights
#      blender_light_scene.py   the LIGHT scene scaffold
#
#  Before running:  hf auth login, then accept THREE licences on HF:
#      black-forest-labs/FLUX.2-dev              (instant)
#      briaai/RMBG-2.0                           (instant)
#      facebook/dinov3-vitl16-pretrain-lvd1689m  (MANUAL - request a day early)
# ============================================================
set -uo pipefail
WS="${WS:-/workspace}"
cd "$WS"

echo "############ 1/4  Blender, Cycles, ComfyUI custom nodes"
bash install-server-stack.sh

echo "############ 2/4  full model set: image + video + 3D  (~180 GB; TIER=lean for a ~20 GB subset)"
WITH_WAN="${WITH_WAN:-1}" bash runpod-3d-setup.sh "${TIER:-48}"

echo "############ 3/4  project layout"
mkdir -p "$WS"/light/{refs,props,renders}
cp -n blender_light_scene.py "$WS/light/" 2>/dev/null || true
echo "  put your reference crops (img_057..img_062) in $WS/light/refs/"

echo "############ 4/4  scene scaffold"
source "$WS/start-xvfb.sh"
blender -b --python "$WS/light/blender_light_scene.py" -- --build

cat <<'DONE'

=== ready ===
From YOUR machine, open the tunnel and keep it up:

    ssh -L 3000:localhost:3000 root@<pod-host> -p <pod-port>

Then point your local MCP at http://127.0.0.1:3000 and the pod's ComfyUI
answers as if it were on your desk. Blender assembly stays local and free;
only the final Cycles render runs here, launched over ssh.

Weights: /workspace/ComfyUI/models    Scene: /workspace/light
HDRI:    /workspace/hdri/studio.exr   Renders: /workspace/light/renders
DONE
