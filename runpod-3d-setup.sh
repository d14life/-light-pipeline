#!/usr/bin/env bash
# ============================================================
#  All-local 3D asset pipeline for ComfyUI. No API, no credits.
#    FLUX.2  ->  multi-reference views  ->  Pixal3D  ->  GLB
#
#  Usage:   bash runpod-3d-setup.sh lean        # ~20 GB - everything the H test needs
#           WITH_WAN=1 bash runpod-3d-setup.sh lean   # +33 GB, adds Wan 2.2 I2V
#           bash runpod-3d-setup.sh 48          # ~110 GB - tier: 16 | 24 | 48 | 80
#           WITH_WAN=1 bash runpod-3d-setup.sh 48
#
#  Volume:  ~110 GB at tier 48  (~180 GB with WITH_WAN=1)
#           ~200 GB at tier 80  (~270 GB with WITH_WAN=1)
#
#  Custom nodes to install in ComfyUI Manager BEFORE running this:
#    Saganaki22/Pixal3D-ComfyUI    <- primary 3D path. Run its "Environment
#         Check" node first: it needs FlashAttention 2/3 and the wheels
#         flex_gemm_ap, cumesh_vb, o_voxel_vb_ap, drtk.
#         NATTEN is only for strict NAF / the Pixal3D-T variant.
#    visualbruno/ComfyUI-Trellis2  <- A/B comparison
#
#  LICENCES - what you may actually SELL output from:
#    MIT / Apache-2.0 and clean: Pixal3D, TRELLIS.2, FLUX.2 klein 4B, Wan 2.2,
#                                BiRefNet
#    FLUX.2 dev: non-commercial. Fine to use, not to sell from - switch the
#                image step to klein 4B if the output is commercial.
#    Hunyuan3D-2.1: opt-in only, its licence excludes the EU, UK and Korea.
#
#  GATED - run `hf auth login`, then accept the licence on each HF page:
#    black-forest-labs/FLUX.2-dev              (auto-approves on accept)
#    facebook/dinov3-vitl16-pretrain-lvd1689m  (MANUAL review by Meta -
#        request access a day BEFORE renting the pod, or Pixal3D/TRELLIS
#        will be missing their image encoder)
# ============================================================
set -uo pipefail

# The pod image marks its dist-packages as externally managed (PEP 668), so a
# plain `pip install` refuses and everything downstream silently has no tools.
# This is a disposable container built for exactly this - override it.
export PIP_BREAK_SYSTEM_PACKAGES=1

TIER="${1:-48}"
CU="${COMFY:-/workspace/ComfyUI}"
WITH_WAN="${WITH_WAN:-0}"

command -v hf >/dev/null || pip install -q -U "huggingface_hub[cli]"
# hf_transfer is a Rust downloader that saturates a datacentre link where the
# python client tops out around 100 MB/s. On 180 GB it is the difference
# between roughly two hours of pod time and forty minutes.
pip install -q -U hf_transfer 2>/dev/null
export HF_HUB_ENABLE_HF_TRANSFER=1
mkdir -p "$CU"/models/{unet,diffusion_models,text_encoders,vae,loras,facebook,trellis2,hunyuan3d,BiRefNet}
mkdir -p "$CU"/models/Pixal3D/TencentARC_Pixal3D

DL_FAILED=0
dl () {
  echo ">>> $1 :: $2"
  if ! hf download "$1" --include "$2" --local-dir "$3"; then
    echo "!! FAILED: $1 $2"
    DL_FAILED=$((DL_FAILED + 1))
  fi
}
# A run where every download failed used to end with a cheerful summary and
# exit 0. Report the count and exit non-zero so a caller can tell.
report () {
  if [ "$DL_FAILED" -gt 0 ]; then
    echo "!! $DL_FAILED download(s) FAILED - see above"
    return 1
  fi
  echo "all downloads succeeded"
}

# hf download preserves repo-relative paths, so "split_files/vae/x" lands at
# models/split_files/vae/x - a folder ComfyUI never scans. Fold it down.
flatten () {
  if [ -d "$CU/models/split_files" ]; then
    (cd "$CU/models/split_files" && for d in */; do
       mkdir -p "$CU/models/$d"
       mv -f "$d"* "$CU/models/$d" 2>/dev/null || true
     done)
    rm -rf "$CU/models/split_files"
    echo "    (flattened split_files/ into models/)"
  fi
}

# ---------------- LEAN: the smallest set that can produce one letter ----------
# Cut on purpose: FLUX.2 dev (35.5G) and its Mistral encoder (24G) - isolating a
# fan onto flat grey does not need a 32B model; Wan (67G) - we render in Cycles,
# not generate video; TRELLIS.2 and Hunyuan3D - those are the A/B pass, not the
# first run. Add them later with `bash runpod-3d-setup.sh 48`.
if [ "$TIER" = "lean" ]; then
  echo "=== lean (~20 GB) -> $CU ==="
  dl unsloth/FLUX.2-klein-4B-GGUF "*Q8_0*.gguf" "$CU/models/unet"
  dl Comfy-Org/vae-text-encorder-for-flux-klein-4b "split_files/*" "$CU/models"
  dl TencentARC/Pixal3D "*" "$CU/models/Pixal3D/TencentARC_Pixal3D"
  dl facebook/dinov3-vitl16-pretrain-lvd1689m "*" "$CU/models/facebook/dinov3-vitl16-pretrain-lvd1689m"
  dl ZhengPeng7/BiRefNet "*" "$CU/models/BiRefNet"
  if [ "$WITH_WAN" = "1" ]; then
    # Wan 2.2 I2V, GGUF Q5 - ~13 GB per expert, loaded one at a time.
    # For adding motion to a finished Cycles frame, not for the registered pair.
    dl QuantStack/Wan2.2-I2V-A14B-GGUF "*HighNoise*Q5_K_M*.gguf" "$CU/models/diffusion_models"
    dl QuantStack/Wan2.2-I2V-A14B-GGUF "*LowNoise*Q5_K_M*.gguf"  "$CU/models/diffusion_models"
    dl Comfy-Org/Wan_2.2_ComfyUI_Repackaged "split_files/text_encoders/umt5*fp8*" "$CU/models"
    dl Comfy-Org/Wan_2.2_ComfyUI_Repackaged "split_files/vae/*"                   "$CU/models"
    dl Kijai/WanVideo_comfy "Lightx2v/lightx2v_I2V_14B_480p_cfg_step_distill_rank64_bf16.safetensors" "$CU/models/loras"
  fi
  flatten
  echo; du -sh "$CU/models"; df -h "$CU"
  report; exit $?
fi

echo "=== tier ${TIER} GB | wan=${WITH_WAN} | -> $CU ==="

# ---------------- STEP 1 : IMAGE ----------------
case "$TIER" in
  80) # true BF16, 64.4 GB. Only fits above ~64 GB VRAM.
      dl black-forest-labs/FLUX.2-dev "flux2-dev.safetensors" "$CU/models/diffusion_models"
      dl Comfy-Org/flux2-dev "split_files/text_encoders/mistral_3_small_flux2_bf16.safetensors" "$CU/models"
      dl Comfy-Org/flux2-dev "split_files/text_encoders/mistral_3_small_flux2_fp8.safetensors"  "$CU/models"
      dl Comfy-Org/flux2-dev "split_files/vae/*" "$CU/models"
      dl Comfy-Org/vae-text-encorder-for-flux-klein-4b "split_files/*" "$CU/models" ;;
  48) # fp8mixed, 35.5 GB. BF16 does NOT fit in 48 GB - do not download it.
      dl Comfy-Org/flux2-dev "split_files/diffusion_models/flux2_dev_fp8mixed.safetensors" "$CU/models"
      dl Comfy-Org/flux2-dev "split_files/text_encoders/mistral_3_small_flux2_fp8.safetensors" "$CU/models"
      dl Comfy-Org/flux2-dev "split_files/vae/*" "$CU/models"
      # Apache-2.0 fallback, for output you intend to sell (repackaged single file):
      dl Comfy-Org/vae-text-encorder-for-flux-klein-4b "split_files/*" "$CU/models" ;;
  24) dl unsloth/FLUX.2-klein-9B-GGUF "*Q6_K*.gguf" "$CU/models/unet"
      dl Comfy-Org/vae-text-encorder-for-flux-klein-9b "split_files/*" "$CU/models" ;;
  16) dl unsloth/FLUX.2-klein-4B-GGUF "*Q8_0*.gguf" "$CU/models/unet"
      dl Comfy-Org/vae-text-encorder-for-flux-klein-4b "split_files/*" "$CU/models" ;;
esac

# ---------------- STEP 2 : VIDEO ORBIT (opt-in) ----------------
# Off by default. Multi-reference editing in FLUX.2 gives consistent views
# without a video model, at a fraction of the compute. Wan 2.2 is the last
# open-weight Wan; 2.5/2.6/2.7 are API-only.
if [ "$WITH_WAN" = "1" ]; then
  if [ "$TIER" -ge 48 ]; then
    dl Comfy-Org/Wan_2.2_ComfyUI_Repackaged "split_files/diffusion_models/wan2.2_i2v_high_noise_14B_fp16.safetensors" "$CU/models"
    dl Comfy-Org/Wan_2.2_ComfyUI_Repackaged "split_files/diffusion_models/wan2.2_i2v_low_noise_14B_fp16.safetensors"  "$CU/models"
  elif [ "$TIER" -ge 24 ]; then
    dl QuantStack/Wan2.2-I2V-A14B-GGUF "*HighNoise*Q5_K_M*.gguf" "$CU/models/diffusion_models"
    dl QuantStack/Wan2.2-I2V-A14B-GGUF "*LowNoise*Q5_K_M*.gguf"  "$CU/models/diffusion_models"
  else
    dl QuantStack/Wan2.2-TI2V-5B-GGUF "*Q6_K*.gguf" "$CU/models/diffusion_models"
  fi
  dl Comfy-Org/Wan_2.2_ComfyUI_Repackaged "split_files/text_encoders/umt5*" "$CU/models"
  dl Comfy-Org/Wan_2.2_ComfyUI_Repackaged "split_files/vae/*"               "$CU/models"
  if [ "$TIER" -lt 48 ]; then
    dl Kijai/WanVideo_comfy "Lightx2v/lightx2v_I2V_14B_480p_cfg_step_distill_rank64_bf16.safetensors" "$CU/models/loras"
  fi
fi

# ---------------- STEP 3 : 3D ----------------
# Pixal3D = Trellis.2 backbone + pixel-aligned back-projection + PBR. MIT.
dl TencentARC/Pixal3D "*" "$CU/models/Pixal3D/TencentARC_Pixal3D"
if [ "$TIER" -ge 48 ]; then
  dl microsoft/TRELLIS.2-4B "*" "$CU/models/trellis2"    # MIT, for A/B
  # Tencent Community Licence: EXPRESSLY DOES NOT APPLY in the EU, UK or South
  # Korea. Opt in with WITH_HUNYUAN=1 only if you are outside those.
  if [ "${WITH_HUNYUAN:-0}" = "1" ]; then
    dl tencent/Hunyuan3D-2.1 "*" "$CU/models/hunyuan3d"
  else
    echo ">>> skipping Hunyuan3D-2.1 (licence excludes EU/UK/KR; WITH_HUNYUAN=1 to fetch)"
  fi
else
  dl ilintar/trellis2-gguf "*Q8*" "$CU/models/trellis2"
fi
dl facebook/dinov3-vitl16-pretrain-lvd1689m "*" "$CU/models/facebook/dinov3-vitl16-pretrain-lvd1689m"
dl ZhengPeng7/BiRefNet "*" "$CU/models/BiRefNet"

flatten
echo; echo "=== what landed ==="
find "$CU/models" \( -name '*.gguf' -o -name '*.safetensors' \) -size +100M -exec du -h {} + | sort -h
du -sh "$CU/models"; df -h "$CU"
report
