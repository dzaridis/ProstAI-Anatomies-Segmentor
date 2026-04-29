<div align="center">

# ProstAI Anatomies Segmentor

**Whole-gland & zonal prostate segmentation from T2-weighted MRI.**
Cascaded nnU-Net v2 · EUCAIM-ready · Single-container, GPU-or-CPU.

[![License: EUPL-1.2](https://img.shields.io/badge/License-EUPL_1.2-1A5FB4.svg)](LICENSE.md)
[![Python 3.9](https://img.shields.io/badge/Python-3.9-3776AB.svg?logo=python&logoColor=white)](https://www.python.org/)
[![nnU-Net v2.2.1](https://img.shields.io/badge/nnU--Net-v2.2.1-EF4444.svg)](https://github.com/MIC-DKFZ/nnUNet)
[![Docker](https://img.shields.io/badge/Docker-multi--stage-2496ED.svg?logo=docker&logoColor=white)](https://www.docker.com/)
[![EUCAIM](https://img.shields.io/badge/EUCAIM-processing--tools-FF6B35.svg)](https://cancerimage.eu/)

</div>

---

A two-stage **nnU-Net v2** pipeline that segments the **whole gland (WG)**, **peripheral zone (PZ)** and **transition zone (TZ)** of the prostate from axial T2-weighted MRI. Packaged as a single, EUCAIM-compliant Docker container — read-only input mount, writable output mount, non-root user (UID 2323), stdout/stderr logging, no network at runtime.

| | |
|---|---|
| **Image** | `harbor.eucaim.cancerimage.eu/processing-tools/prostate-zone-segmentor` |
| **Modality / Anatomy** | T2-weighted MRI · Prostate (WG, PZ, TZ) |
| **Input** | DICOM (EUCAIM CDM) **or** flat NIfTI |
| **Output** | NIfTI binary masks · optional probability maps · optional DICOM-SEG · `results.json` |
| **License** | [EUPL-1.2](LICENSE.md) |

## Quick start

```bash
docker pull harbor.eucaim.cancerimage.eu/processing-tools/prostate-zone-segmentor:<tag>

# DICOM input (EUCAIM CDM layout)
docker run --rm --gpus all \
  -v /path/to/dicom:/input:ro -v /path/to/out:/output \
  harbor.eucaim.cancerimage.eu/processing-tools/prostate-zone-segmentor:<tag> \
    --input /input --output /output

# Flat NIfTI input
docker run --rm --gpus all \
  -v /path/to/niftis:/input:ro -v /path/to/out:/output \
  harbor.eucaim.cancerimage.eu/processing-tools/prostate-zone-segmentor:<tag> \
    --input /input --output /output --input-format nifti

# CPU-only (≈30× slower)
docker run --rm \
  -v /path/to/input:/input:ro -v /path/to/out:/output \
  harbor.eucaim.cancerimage.eu/processing-tools/prostate-zone-segmentor:<tag> \
    --input /input --output /output --device cpu
```

Sample data and one-line test commands live in [`examples/`](examples/).
Local Windows + CPU walkthrough: [`LOCAL_TESTING_WINDOWS_CPU.md`](LOCAL_TESTING_WINDOWS_CPU.md).

## Inputs

**EUCAIM CDM (preferred):**

```
/input/<subjectId>/<studyId>/<seriesId>/*.dcm
/input/index.json   (optional)
```

**Flat NIfTI (testing):**

```
/input/<case_id>.nii.gz
```

## Outputs

```
/output/
├── results.json                          ← machine-readable run index
└── <subjectId>/<studyId>/
    ├── wg_binary.nii.gz                  ← whole-gland mask (input grid)
    ├── pz_binary.nii.gz                  ← peripheral-zone mask
    ├── tz_binary.nii.gz                  ← transition-zone mask
    ├── {wg,pz,tz}_probs.nii.gz           ← (--save-probs)
    └── prostate_zones_seg.dcm            ← multi-segment DICOM-SEG (DICOM input)
```

Exit code `0` if all cases succeeded, `1` if any case failed (per-case status in `results.json`).

## CLI

| Flag | Default | Description |
|---|---|---|
| `--input`, `-i` | *required* | Read-only input directory. |
| `--output`, `-o` | *required* | Writable output directory. |
| `--input-format` | `auto` | `auto` \| `dicom` \| `nifti`. |
| `--save-probs` | off | Also write `*_probs.nii.gz`. |
| `--save-dicom-seg` / `--no-save-dicom-seg` | on | Toggle DICOM-SEG export. |
| `--device` | `auto` | `auto` \| `cuda` \| `cpu`. |
| `--log-level` | `INFO` | `DEBUG` \| `INFO` \| `WARNING` \| `ERROR`. |

## Requirements

| | Minimum | Recommended |
|---|---|---|
| **GPU** | NVIDIA, CC ≥ 6.0, 8 GB VRAM (CUDA 11.7) | 12 GB+ VRAM |
| **CPU** | 4 cores | 8 cores |
| **RAM** | 8 GB | 16 GB |
| **Disk** | 10 GB | 20 GB |
| **Network** | none at runtime | — |

## Citing

If you use this tool, please cite the underlying methodology:

1. Zaridis D. I., Mylona E., Tachos N. S., Kalantzopoulos C., Tsiknakis N., Marias K., Tsiknakis M., Fotiadis D. I. *Region-adaptive magnetic resonance image enhancement for improving CNN-based segmentation of the prostate and prostatic zones.* Biomedical Signal Processing and Control, 2024. <https://www.sciencedirect.com/science/article/pii/S1746809424002453>

2. Zaridis D., Mylona E., Tachos N., Pezoulas V. C., Grigoriadis G., Tsiknakis N., Marias K., Tsiknakis M., Fotiadis D. I. *Region-adaptive magnetic resonance image enhancement for improving CNN-based segmentation of the prostate.* IEEE EMBC 2022. <https://ieeexplore.ieee.org/abstract/document/9926929>

## Authors

**Dimitrios Zaridis** *(corresponding)* · `dimzaridis@gmail.com` · M.Eng, PhD candidate, NTUA
Charalampos Kalantzopoulos · Eugenia Mylona, PhD · Nikolaos S. Tachos, PhD
**Dimitrios I. Fotiadis**, Professor of Biomedical Technology, University of Ioannina

## License

This project is licensed under the **European Union Public Licence v. 1.2 (EUPL-1.2)** — see [`LICENSE.md`](LICENSE.md) for the full text. Canonical: <https://joinup.ec.europa.eu/collection/eupl/>

## Acknowledgement

Packaged for the **EUCAIM** (European Cancer Imaging) federated processing infrastructure following the *Research Software Packaging for FAIR and Reproducible Analysis in EUCAIM* guide v1.2.
