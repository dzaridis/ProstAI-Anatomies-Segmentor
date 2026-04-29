# Local Testing — Windows + CPU

Step-by-step guide to build and run the **ProstAI Anatomies Segmentor** container on a Windows machine **without** an NVIDIA GPU. All commands assume PowerShell run from the repo root:

```
D:\EUCAIM Tools\MRI-Prostate-Gland-and-Zone-Segmentor
```

> CPU inference is **~30× slower** per case than GPU. A single T2-weighted volume takes roughly **5–15 minutes** on a modern desktop CPU. Use 1–2 patients for testing, not the whole dataset.

---

## 1. Prerequisites

- Docker Desktop for Windows (WSL2 backend recommended)
- Repo cloned locally
- Patient data restored under `Pats/` (1 NIfTI + 3 DICOM patients)

Verify Docker is running:

```powershell
docker version
```

---

## 2. Build the image

```powershell
docker build -t prostate-zone-segmentor:dev .
```

First build: 15–30 min. Subsequent builds reuse cached layers.

Verify it built:

```powershell
docker images prostate-zone-segmentor
```

---

## 3. Smoke test — CLI only

Confirm the entrypoint works (instant, no inference):

```powershell
docker run --rm prostate-zone-segmentor:dev --help
```

You should see the `argparse` help with all flags (`--input`, `--output`, `--input-format`, `--save-probs`, `--save-dicom-seg`, `--device`, `--log-level`).

---

## 4. Test on the NIfTI patient (CPU)

### 4.1 Prepare input/output folders

```powershell
New-Item -ItemType Directory -Force -Path test_input_nii  | Out-Null
New-Item -ItemType Directory -Force -Path test_output_nii | Out-Null
Copy-Item "Pats\PCa-100280262407226510129745299155934395567.nii.gz" -Destination test_input_nii\
```

### 4.2 Run

```powershell
docker run --rm `
  -v "${PWD}\test_input_nii:/input:ro" `
  -v "${PWD}\test_output_nii:/output" `
  prostate-zone-segmentor:dev `
    --input /input `
    --output /output `
    --input-format nifti `
    --device cpu `
    --log-level INFO
```

Expected runtime: ~5–15 min on CPU.

### 4.3 Inspect outputs

```powershell
Get-Content test_output_nii\results.json
Get-ChildItem -Recurse test_output_nii
```

Expected layout:

```
test_output_nii\
├── results.json
└── PCa-100280262407226510129745299155934395567\
    └── PCa-100280262407226510129745299155934395567\
        ├── wg_binary.nii.gz
        ├── pz_binary.nii.gz
        └── tz_binary.nii.gz
```

---

## 5. Test on the DICOM patients (CPU)

### 5.1 Pick ONE patient first (faster than running all three)

```powershell
New-Item -ItemType Directory -Force -Path test_input_dcm  | Out-Null
New-Item -ItemType Directory -Force -Path test_output_dcm | Out-Null
Copy-Item -Recurse "Pats\dicom_dataset\PCa-137682045087109883822290509365021163379" `
                   -Destination test_input_dcm\
```

### 5.2 Run

```powershell
docker run --rm `
  -v "${PWD}\test_input_dcm:/input:ro" `
  -v "${PWD}\test_output_dcm:/output" `
  prostate-zone-segmentor:dev `
    --input /input `
    --output /output `
    --device cpu `
    --log-level INFO
```

### 5.3 Inspect outputs

```powershell
Get-Content test_output_dcm\results.json
Get-ChildItem -Recurse test_output_dcm
```

Expected layout for each patient:

```
test_output_dcm\
├── results.json
└── PCa-137682045087109883822290509365021163379\
    └── 1.3.6.1.4.1.58108.1.128273...\
        ├── wg_binary.nii.gz
        ├── pz_binary.nii.gz
        ├── tz_binary.nii.gz
        └── prostate_zones_seg.dcm     ← multi-segment DICOM-SEG
```

---

## 6. Run on ALL three DICOM patients

If the single-patient test passed and you have time:

```powershell
docker run --rm `
  -v "${PWD}\Pats\dicom_dataset:/input:ro" `
  -v "${PWD}\test_output_dcm_all:/output" `
  prostate-zone-segmentor:dev `
    --input /input `
    --output /output `
    --device cpu
```

Expected runtime: ~15–45 min (3 patients × ~5–15 min each).

---

## 7. Optional flags worth testing

### 7.1 Save probability maps

```powershell
docker run --rm `
  -v "${PWD}\test_input_nii:/input:ro" `
  -v "${PWD}\test_output_nii_probs:/output" `
  prostate-zone-segmentor:dev `
    --input /input --output /output --input-format nifti --device cpu --save-probs
```

Adds `wg_probs.nii.gz`, `pz_probs.nii.gz`, `tz_probs.nii.gz` per case.

### 7.2 Disable DICOM-SEG export

```powershell
docker run --rm `
  -v "${PWD}\test_input_dcm:/input:ro" `
  -v "${PWD}\test_output_dcm_nosg:/output" `
  prostate-zone-segmentor:dev `
    --input /input --output /output --device cpu --no-save-dicom-seg
```

Skips the `prostate_zones_seg.dcm` file.

### 7.3 More verbose logs

Append `--log-level DEBUG` to any of the above for full nnU-Net verbosity.

---

## 8. Cleanup

Remove test artefacts:

```powershell
Remove-Item -Recurse -Force test_input_nii, test_output_nii, test_input_dcm, test_output_dcm, test_output_dcm_all, test_output_nii_probs, test_output_dcm_nosg -ErrorAction SilentlyContinue
```

Remove the dev image:

```powershell
docker rmi prostate-zone-segmentor:dev
```

Remove dangling builder layers (frees ~10 GB):

```powershell
docker builder prune -f
```

---

## 9. Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| `docker: Mounts denied: ... is not shared` | Drive D: not shared with Docker Desktop | Settings → Resources → File Sharing → add `D:\` → Apply & Restart |
| `permission denied` writing to `/output` | Host folder has restrictive ACLs | Run PowerShell as administrator, or `icacls test_output_nii /grant Everyone:F /T` |
| `RuntimeError: CUDA error` | Container tried to use GPU on a CPU-only host | You forgot `--device cpu` |
| `No DICOM series or .nii.gz files found` | Wrong input layout | Verify `ls test_input_dcm` actually contains the patient subfolder |
| Build hangs at `pip install` for >20 min | Slow network pulling torch wheels | Wait it out — torch wheel is ~2 GB |
| `groupadd: not found` during build | Should already be fixed; if you still see it, re-pull this branch | — |

---

## 10. What to send if something breaks

Capture the failing run with full debug logging redirected to a file:

```powershell
docker run --rm `
  -v "${PWD}\test_input_nii:/input:ro" `
  -v "${PWD}\test_output_nii:/output" `
  prostate-zone-segmentor:dev `
    --input /input --output /output --input-format nifti --device cpu --log-level DEBUG `
  *> run.log

Get-Content run.log -Tail 100
```

Share `run.log` (or just the last 100 lines) for debugging.
