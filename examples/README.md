# Examples

Sample inputs for local testing and CI.

| Folder | Format | Cases | Use |
|---|---|---|---|
| `nifti/` | `.nii.gz` (axial T2-weighted MRI) | 1 | Fast smoke test (CPU runs in 5–10 min). |
| `dicom/` | DICOM series, EUCAIM-CDM-style layout | 3 patients | Full DICOM ↔ DICOM-SEG round-trip test. |

## Quick run (NIfTI)

```bash
docker run --rm \
  -v "$(pwd)/examples/nifti:/input:ro" \
  -v "$(pwd)/out_nifti:/output" \
  prostate-zone-segmentor:dev \
    --input /input --output /output --input-format nifti --device cpu
```

## Quick run (DICOM)

```bash
docker run --rm \
  -v "$(pwd)/examples/dicom:/input:ro" \
  -v "$(pwd)/out_dicom:/output" \
  prostate-zone-segmentor:dev \
    --input /input --output /output --device cpu
```

The CI workflow at `.github/workflows/ci.yml` exercises the NIfTI sample on every push.
