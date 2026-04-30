# Examples

Sample inputs for local testing and CI.

| Folder | Format | Cases | Use |
|---|---|---|---|
| `nifti/` | `.nii.gz` (axial T2 only) | 1 | Fast smoke test (CPU runs in 5–10 min); WG/PZ/TZ only. |
| `dicom/` | DICOM series, T2 only | 3 patients | DICOM ↔ DICOM-SEG round-trip; WG/PZ/TZ only. |
| `dicom_lesion/` | DICOM series with `t2_series/`, `adc_series/`, `dwi_series/` | 1 patient | Full pipeline incl. ProLesA-Net lesion stage. |

## Quick run (NIfTI, T2 only)

```bash
docker run --rm \
  -v "$(pwd)/examples/nifti:/input:ro" \
  -v "$(pwd)/out_nifti:/output" \
  prostate-zone-segmentor:dev \
    --input /input --output /output --input-format nifti --device cpu \
    --no-save-lesion
```

## Quick run (DICOM, T2 only)

```bash
docker run --rm \
  -v "$(pwd)/examples/dicom:/input:ro" \
  -v "$(pwd)/out_dicom:/output" \
  prostate-zone-segmentor:dev \
    --input /input --output /output --device cpu --no-save-lesion
```

## Quick run (DICOM, full pipeline with lesion)

```bash
docker run --rm \
  -v "$(pwd)/examples/dicom_lesion:/input:ro" \
  -v "$(pwd)/out_dicom_lesion:/output" \
  prostate-zone-segmentor:dev \
    --input /input --output /output --input-format dicom --device cpu
```

The CI workflow at `.github/workflows/ci.yml` exercises the NIfTI sample on every push.
