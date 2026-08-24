"""BiRefNet cutout. MIT, so the pipeline stays clean where RMBG (CC BY-NC) would not."""
import sys, torch
from PIL import Image
from torchvision import transforms
from transformers import AutoModelForImageSegmentation

src, dst = sys.argv[1], sys.argv[2]
m = AutoModelForImageSegmentation.from_pretrained(
    "/workspace/ComfyUI/models/BiRefNet", trust_remote_code=True)
m.to("cuda").half().eval()
torch.set_float32_matmul_precision("high")

im = Image.open(src).convert("RGB")
tf = transforms.Compose([transforms.Resize((1024, 1024)), transforms.ToTensor(),
                         transforms.Normalize([.485,.456,.406],[.229,.224,.225])])
with torch.no_grad():
    pred = m(tf(im).unsqueeze(0).to("cuda").half())[-1].sigmoid().cpu()[0].squeeze()
# A soft edge is not kindness here: Pixal3D treats any non-zero alpha as
# matter, so a feathered background becomes a slab of geometry behind the
# subject. Threshold hard, then erode a pixel to kill the halo.
import numpy as np
from PIL import ImageFilter
m = np.array(transforms.ToPILImage()(pred).resize(im.size))
m = (m > 128).astype("uint8") * 255
mask = Image.fromarray(m).filter(ImageFilter.MinFilter(3))
# MoGe estimates the camera from RGB, and it never sees the alpha - so a floor
# and a backdrop still visible there come back as a slab of geometry behind the
# subject. Flatten the background to one flat colour and MoGe has no plane to
# find, while alpha still tells Pixal3D what is actually the object.
flat = Image.new("RGB", im.size, (128, 128, 128))
out = Image.composite(im, flat, mask)
out.putalpha(mask)
out.save(dst)
import numpy as np
a = np.array(mask)
print(f"cutout ok -> {dst}  subject covers {100*(a>127).mean():.1f}% of frame")
