# Gates: local setup

OWNS: blender_light_scene.py, look.py, checks/**, *.sh

Scope: everything claimed as finished on the PC before any pod is rented.
Each gate re-proves a claim that was previously made in prose.

- [x] G1: the scene scaffold builds with the case/word/board/loop groups
  CHECK: python checks/verify_setup.py scaffold
  EXPECT: scaffold verification passed
  EVIDENCE: exit=0; shell=C:\Windows\system32\cmd.exe; cwd=C:\Users\D1\Downloads\light-pipeline; path=af8571194fcc/51 entries; output=scaffold verification passed (4 groups, 24 placeholders)

- [x] G2: look.py reports tris, UVs and materials for a GLB, and writes a readable sheet
  CHECK: python checks/verify_setup.py look-glb
  EXPECT: glb inspection verification passed
  EVIDENCE: exit=0; shell=C:\Windows\system32\cmd.exe; cwd=C:\Users\D1\Downloads\light-pipeline; path=af8571194fcc/51 entries; output=glb inspection verification passed

- [x] G3: look.py turns a real clip into a frame sheet
  CHECK: python checks/verify_setup.py look-video
  EXPECT: video inspection verification passed
  EVIDENCE: exit=0; shell=C:\Windows\system32\cmd.exe; cwd=C:\Users\D1\Downloads\light-pipeline; path=af8571194fcc/51 entries; output=video inspection verification passed (1260x840 sheet)

- [x] G4: pod scripts are LF and valid bash
  CHECK: python checks/verify_setup.py line-endings
  EXPECT: line ending verification passed
  EVIDENCE: exit=0; shell=C:\Windows\system32\cmd.exe; cwd=C:\Users\D1\Downloads\light-pipeline; path=af8571194fcc/51 entries; output=line ending verification passed (3 scripts, LF, syntax clean)

- [x] G5: Cycles has a real GPU backend, not a silent CPU fallback
  CHECK: python checks/verify_setup.py blender-gpu
  EXPECT: gpu verification passed
  EVIDENCE: exit=0; shell=C:\Windows\system32\cmd.exe; cwd=C:\Users\D1\Downloads\light-pipeline; path=af8571194fcc/51 entries; output=gpu verification passed (HIP: AMD Radeon RX 6650 XT)

- [x] G6: conditioning decimates, keeps UVs, corrects metalness and sets real scale
  CHECK: python checks/verify_setup.py conditioning
  EXPECT: conditioning verification passed
  EVIDENCE: exit=0; shell=C:\Windows\system32\cmd.exe; cwd=C:\Users\D1\Downloads\light-pipeline; path=af8571194fcc/51 entries; output=conditioning verification passed (400 tris, 0.12 m, uv kept, web 10.3 KB)
