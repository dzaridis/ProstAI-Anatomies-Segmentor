<div align="center">

# ProstAI Anatomies Segmentor

**Whole-gland, zonal & lesion prostate segmentation from multi-parametric MRI.**
Cascaded nnU-Net v2 (anatomies) + ProLesA-Net (lesions) · EUCAIM-ready · Single-container, GPU-or-CPU.

[![License: EUPL-1.2](https://img.shields.io/badge/License-EUPL_1.2-1A5FB4.svg)](LICENSE.md)
[![Python 3.9](https://img.shields.io/badge/Python-3.9-3776AB.svg?logo=python&logoColor=white)](https://www.python.org/)
[![nnU-Net v2.2.1](https://img.shields.io/badge/nnU--Net-v2.2.1-EF4444.svg)](https://github.com/MIC-DKFZ/nnUNet)
[![Docker](https://img.shields.io/badge/Docker-multi--stage-2496ED.svg?logo=docker&logoColor=white)](https://www.docker.com/)
[![EUCAIM](https://img.shields.io/badge/EUCAIM-processing--tools-FF6B35.svg)](https://cancerimage.eu/)

</div>

---

A three-stage pipeline that segments the **whole gland (WG)**, **peripheral zone (PZ)**, **transition zone (TZ)** and (when ADC + DWI are provided) the **prostate lesions** from prostate MRI. The anatomies are produced by two cascaded **nnU-Net v2** models on T2; the lesion mask is produced by **ProLesA-Net** (Keras / TensorFlow 2.11) operating on T2 + ADC + DWI inside the WG mask. Packaged as a single, EUCAIM-compliant Docker container — read-only input mount, writable output mount, non-root user (UID 2323), stdout/stderr logging, no network at runtime.

| | |
|---|---|
| **Image** | `harbor.eucaim.cancerimage.eu/processing-tools/prostate-anatomies-and-lesion-segmentor` |
| **Modality / Anatomy** | mp-MRI (T2 + ADC + DWI) · Prostate (WG, PZ, TZ, Lesion) |
| **Input** | DICOM (EUCAIM CDM) **or** NIfTI (`T2*.nii.gz` + optional `ADC*.nii.gz`, `DWI*.nii.gz`) |
| **Output** | NIfTI binary masks · optional probability maps · optional DICOM-SEG · `results.json` |
| **License** | [EUPL-1.2](LICENSE.md) |

## Quick start

```bash
docker pull harbor.eucaim.cancerimage.eu/processing-tools/prostate-anatomies-and-lesion-segmentor:<tag>

# DICOM input (EUCAIM CDM layout)
docker run --rm --gpus all \
  -v /path/to/dicom:/input:ro -v /path/to/out:/output \
  harbor.eucaim.cancerimage.eu/processing-tools/prostate-anatomies-and-lesion-segmentor:<tag> \
    --input /input --output /output

# Flat NIfTI input
docker run --rm --gpus all \
  -v /path/to/niftis:/input:ro -v /path/to/out:/output \
  harbor.eucaim.cancerimage.eu/processing-tools/prostate-anatomies-and-lesion-segmentor:<tag> \
    --input /input --output /output --input-format nifti

# CPU-only (≈30× slower)
docker run --rm \
  -v /path/to/input:/input:ro -v /path/to/out:/output \
  harbor.eucaim.cancerimage.eu/processing-tools/prostate-anatomies-and-lesion-segmentor:<tag> \
    --input /input --output /output --device cpu
```

Sample data and one-line test commands live in [`examples/`](examples/).
Local Windows + CPU walkthrough: [`LOCAL_TESTING_WINDOWS_CPU.md`](LOCAL_TESTING_WINDOWS_CPU.md).

## Inputs

**EUCAIM CDM DICOM (preferred):**

```
/input/<patient>/<study>/t2_series/*.dcm         # required
/input/<patient>/<study>/adc_series/*.dcm        # optional → enables lesion stage
/input/<patient>/<study>/dwi_series/*.dcm        # optional → enables lesion stage
/input/index.json                                # optional
```

**NIfTI per patient (recommended NIfTI layout, mirrors the DICOM tree):**

```
/input/<patient>/t2_series.nii.gz                # required
/input/<patient>/adc_series.nii.gz               # optional → enables lesion stage
/input/<patient>/dwi_series.nii.gz               # optional → enables lesion stage
```

(`/input/<patient>/<study>/{t2,adc,dwi}_series.nii.gz` is also accepted.)

**NIfTI flat (legacy, single-file smoke test, no lesion):**

```
/input/<case_id>.nii.gz
```

The lesion stage runs only for cases where **both** an ADC and a DWI sibling
are discovered next to the T2 volume; otherwise the case is processed for
WG/PZ/TZ only. The two anatomies models (WG and zonal) need only the T2
volume.

## Outputs

```
/output/
├── results.json                          ← machine-readable run index
└── <subjectId>/<studyId>/
    ├── wg_binary.nii.gz                  ← whole-gland mask (input grid)
    ├── pz_binary.nii.gz                  ← peripheral-zone mask
    ├── tz_binary.nii.gz                  ← transition-zone mask
    ├── lesion_binary.nii.gz              ← lesion mask (only if ADC + DWI present)
    ├── {wg,pz,tz,lesion}_probs.nii.gz    ← (--save-probs)
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
| `--save-lesion` / `--no-save-lesion` | on | Toggle the ProLesA-Net lesion stage (needs ADC + DWI). |
| `--lesion-threshold` | `0.1` | Probability threshold used to binarise the lesion mask. |
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

If you use this tool, please cite the underlying methodologies:

1. D. Zaridis, E. Mylona, N. Tachos, K. Marias, M. Tsiknakis and D. I. Fotiadis, "Fine-tuned feature selection to improve prostate segmentation via a fully connected meta-learner architecture," 2022 IEEE-EMBS International Conference on Biomedical and Health Informatics (BHI), Ioannina, Greece, 2022, pp. 01-04, doi: 10.1109/BHI56158.2022.9926929. keywords: {Deep learning;Sensitivity;Magnetic resonance imaging;Glands;Feature extraction;Complexity theory;Prostate cancer;Prostate Segmentation;Deep Learning;Ensembling;Fine Tuning},


2. Zaridis, Dimitrios I., et al. "ResQu-Net: Effective prostate’s peripheral zone segmentation leveraging the representational power of attention-based mechanisms." Biomedical Signal Processing and Control 93 (2024): 106187.

3. Zaridis, Dimitrios I., et al. "ProLesA-Net: A multi-channel 3D architecture for prostate MRI lesion segmentation with multi-scale channel and spatial attentions." *Patterns* 5.8 (2024): 101031, doi: 10.1016/j.patter.2024.101031.

## Authors

**Dimitrios Zaridis** *(corresponding)* · `dimzaridis@gmail.com` · PhD
Charalampos Kalantzopoulos · Eugenia Mylona, PhD · Nikolaos S. Tachos, PhD
**Dimitrios I. Fotiadis**, Professor of Biomedical Technology, University of Ioannina

## License

This project is licensed under the **European Union Public Licence v. 1.2 (EUPL-1.2)** — see [`LICENSE.md`](LICENSE.md) for the full text. Canonical: <https://joinup.ec.europa.eu/collection/eupl/>

