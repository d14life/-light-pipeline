#!/usr/bin/env bash
# ============================================================
#  Pod side only: Blender + Cycles on GPU, and the ComfyUI custom nodes.
#
#  No Claude Code here on purpose. Claude runs on your PC and reaches this box
#  over SSH, which keeps your local files (refs, site, repo) visible to it at
#  the same time as the pod. Forward the ComfyUI port from your machine:
#
#      ssh -L 3000:localhost:3000 root@<pod> -p <port>
#
#  Then a local MCP server pointed at http://127.0.0.1:3000 drives the pod's
#  ComfyUI as if it were local. Blender assembly stays on your PC; only the
#  final Cycles render runs here, launched over ssh.
#
#  Base image: Runpod Pytorch 2.8.0 is a good choice - Pixal3D's prebuilt CUDA
#  wheels target torch 2.7/2.8. ComfyUI is installed on top by this script.
#
#  STORAGE: use a NETWORK VOLUME, not a "volume disk". A volume disk is tied to
#  the pod's lifecycle and takes 180 GB of weights with it when the pod is
#  terminated. Create the network volume under Storage first, then attach it.
#
#  Run:  bash install-server-stack.sh
#        BLENDER_VER=4.5.4 bash install-server-stack.sh     # keep in step with your PC
# ============================================================
set -uo pipefail

WS="${WS:-/workspace}"
CU="${COMFY:-$WS/ComfyUI}"
BLENDER_VER="${BLENDER_VER:-4.5.3}"   # matched to the PC: a .blend must
BL_MAJ="${BLENDER_VER%.*}"           # open on both ends of the pipeline
BL_DIR="$WS/blender"

echo "### 1/5  system libs (Blender links these even in background mode)"
apt-get update -qq
apt-get install -y -qq --no-install-recommends \
  xz-utils xvfb libx11-6 libxi6 libxxf86vm1 libxrender1 libxfixes3 \
  libgl1 libsm6 libice6 libglu1-mesa libegl1 libxkbcommon0 curl git ca-certificates

echo "### 2/5  Blender ${BLENDER_VER} -> ${BL_DIR}"
# Official tarball. Never apt - the packaged Blender is years behind.
if [ ! -x "$BL_DIR/blender" ]; then
  mkdir -p "$BL_DIR"
  URL="https://download.blender.org/release/Blender${BL_MAJ}/blender-${BLENDER_VER}-linux-x64.tar.xz"
  echo "    $URL"
  curl -fL "$URL" -o /tmp/bl.tar.xz || { echo "!! download failed - check download.blender.org/release/ for the current version"; exit 1; }
  tar -xJf /tmp/bl.tar.xz -C "$BL_DIR" --strip-components=1
  rm -f /tmp/bl.tar.xz
fi
ln -sf "$BL_DIR/blender" /usr/local/bin/blender
blender --version | head -2

cat > "$WS/start-xvfb.sh" <<'XV'
#!/usr/bin/env bash
pgrep -x Xvfb >/dev/null || (Xvfb :99 -screen 0 1920x1080x24 -ac +extension GLX +render -noreset &)
export DISPLAY=:99
XV
chmod +x "$WS/start-xvfb.sh"
source "$WS/start-xvfb.sh"

echo "### 3/5  Cycles on the GPU"
cat > "$WS/enable_gpu.py" <<'PY'
import bpy
p = bpy.context.preferences.addons['cycles'].preferences
for backend in ('OPTIX', 'CUDA', 'HIP'):
    try:
        p.compute_device_type = backend
        p.get_devices()
        devs = [d for d in p.devices if d.type == backend]
        if devs:
            for d in p.devices:
                d.use = (d.type == backend)
            print(f"[gpu] {backend}: " + ", ".join(d.name for d in devs))
            break
    except Exception as e:
        print(f"[gpu] {backend} unavailable: {e}")
else:
    print("[gpu] !! no GPU backend - Cycles would fall back to CPU")
bpy.context.scene.cycles.device = 'GPU'
bpy.ops.wm.save_userpref()
PY
blender -b --python "$WS/enable_gpu.py" 2>&1 | grep -E '^\[gpu\]'

echo "### 4/5  ComfyUI + custom nodes"
# The Pytorch 2.8.0 template ships no ComfyUI, and that is the better base:
# Pixal3D's prebuilt CUDA wheels target torch 2.7/2.8, and a ready-made ComfyUI
# image often pins something else. Install ComfyUI on top instead of fighting it.
if [ ! -d "$CU" ]; then
  echo "    no ComfyUI at $CU - installing it"
  git clone --depth 1 https://github.com/comfyanonymous/ComfyUI "$CU"     || { echo "!! ComfyUI clone failed"; exit 1; }
  # torch is already in the image; installing ComfyUI's pin would downgrade it
  # and break the wheels, so drop it from the requirements before installing.
  grep -viE '^(torch|torchvision|torchaudio)([=<>~!]|$)' "$CU/requirements.txt"     > /tmp/comfy-req.txt
  pip install -q -r /tmp/comfy-req.txt 2>&1 | tail -2
  python -c "import torch; print(f'    torch {torch.__version__}, cuda {torch.version.cuda}')"
fi
if [ ! -d "$CU" ]; then
  echo "!! ComfyUI still missing at $CU"
else
  CN="$CU/custom_nodes"; mkdir -p "$CN"
  clone () {  # clone <url> <dir> [noreqs]
    if [ -d "$CN/$2" ]; then echo "    have $2"; else
      git clone --depth 1 "$1" "$CN/$2" && echo "    got $2" || echo "!! clone failed: $2"
    fi
    if [ "${3:-}" != "noreqs" ] && [ -f "$CN/$2/requirements.txt" ]; then
      pip install -q -r "$CN/$2/requirements.txt" 2>&1 | tail -1
    fi
  }
  # ComfyUI-GGUF is not optional: without it the klein GGUF will not load at all.
  clone https://github.com/city96/ComfyUI-GGUF            ComfyUI-GGUF
  clone https://github.com/Saganaki22/Pixal3D-ComfyUI     Pixal3D-ComfyUI  noreqs   # reqs can start a flash-attn source build; use its Environment Check + prebuilt wheels instead
  clone https://github.com/visualbruno/ComfyUI-Trellis2   ComfyUI-Trellis2
  clone https://github.com/kijai/ComfyUI-WanVideoWrapper  ComfyUI-WanVideoWrapper

  echo
  echo "    NEXT, BEFORE DOWNLOADING WEIGHTS: run Pixal3D's 'Environment Check' node."
  echo "    It reports which CUDA wheels are missing - flex_gemm_ap, cumesh_vb,"
  echo "    o_voxel_vb_ap, drtk, plus FlashAttention 2 or 3. Install those first,"
  echo "    or you will download ~180 GB and then find the node cannot run."
  echo "    Pixal3D also pulls MoGe and a NAF upsampler on first use; let it."
fi

echo "### 5/5  an HDRI, because transmission needs something to refract"
# Glass with nothing around it renders as grey plastic. One 4K studio probe is
# enough for the letter shells; swap it for a scene-matched probe later.
mkdir -p "$WS/hdri"
if [ ! -s "$WS/hdri/studio.exr" ]; then
  curl -fL "https://dl.polyhaven.org/file/ph-assets/HDRIs/exr/4k/studio_small_09_4k.exr" \
       -o "$WS/hdri/studio.exr" || echo "!! HDRI download failed - grab any 4k .exr from polyhaven.com into $WS/hdri/"
fi
ls -lh "$WS/hdri/" 2>/dev/null

cat <<'DONE'

=== pod ready ===
  source /workspace/start-xvfb.sh

From YOUR machine, to drive this box:
  ssh -L 3000:localhost:3000 root@<pod-host> -p <pod-port>

Render, once a scene exists:
  ssh root@<pod> "blender -b /workspace/light/light.blend --python-expr \
    'import bpy;exec(open(\"/workspace/light/blender_light_scene.py\").read())'"
  rsync -av root@<pod>:/workspace/light/renders/ ./renders/
DONE
