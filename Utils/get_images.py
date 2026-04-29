"""
Discover input studies under an input directory and return structured records.

Two layouts are supported:
  1. EUCAIM CDM (preferred):
        <input_dir>/<subjectId>/<studyId>/<seriesId>/*.dcm
        <input_dir>/index.json   (optional)
  2. Flat NIfTI (back-compat / testing):
        <input_dir>/*.nii.gz

The function returns a list of records:
    {
      "case_id":      str,   # used as filename stem in outputs
      "subject_id":   str,
      "study_id":     str,
      "nifti_path":   str,   # NIfTI path the segmentor will read
      "source_dicom_dir": Optional[str],   # set only when the input was DICOM
    }
"""

import json
import logging
import os
import tempfile
from pathlib import Path
from typing import List, Dict, Optional

from SimpleITK import (
    ImageSeriesReader,
    WriteImage,
    ImageSeriesReader_GetGDCMSeriesFileNames as GetGDCMSeriesFileNames,
)

LOGGER = logging.getLogger(__name__)


def _read_dcm_series(dicom_files):
    reader = ImageSeriesReader()
    reader.SetFileNames(dicom_files)
    reader.MetaDataDictionaryArrayUpdateOn()
    reader.LoadPrivateTagsOn()
    return reader.Execute()


def _convert_dicom_dir_to_nifti(dicom_dir: str, scratch_dir: str, case_id: str) -> Optional[str]:
    files = GetGDCMSeriesFileNames(dicom_dir)
    if len(files) <= 1:
        LOGGER.warning("Skipping %s: needs ≥2 DICOM files (multi-frame not supported).", dicom_dir)
        return None
    image = _read_dcm_series(files)
    out_path = os.path.join(scratch_dir, f"{case_id}.nii.gz")
    WriteImage(image, out_path)
    return out_path


def _detect_dicom_studies(input_dir: str) -> List[Dict[str, str]]:
    """Walks input_dir; emits a record per series directory containing .dcm files."""
    records = []
    seen = set()
    for dirpath, _, files in os.walk(input_dir):
        if any(f.lower().endswith(".dcm") for f in files):
            if dirpath in seen:
                continue
            seen.add(dirpath)
            rel = os.path.relpath(dirpath, input_dir).split(os.sep)
            if len(rel) >= 3:
                subject_id, study_id, series_id = rel[0], rel[1], rel[-1]
            elif len(rel) == 2:
                subject_id, study_id, series_id = rel[0], rel[1], rel[1]
            else:
                subject_id = study_id = series_id = rel[-1] if rel and rel[0] != "." else "unknown"
            records.append(
                {
                    "subject_id": subject_id,
                    "study_id": study_id,
                    "series_id": series_id,
                    "dicom_dir": dirpath,
                }
            )
    return records


def _detect_niftis(input_dir: str) -> List[Dict[str, str]]:
    records = []
    for dirpath, _, files in os.walk(input_dir):
        for f in files:
            if f.endswith(".nii.gz"):
                stem = f[: -len(".nii.gz")]
                records.append(
                    {
                        "subject_id": stem,
                        "study_id": stem,
                        "nifti_path": os.path.join(dirpath, f),
                    }
                )
    return records


def discover_inputs(
    input_dir: str,
    input_format: str = "auto",
    scratch_dir: Optional[str] = None,
) -> List[Dict[str, Optional[str]]]:
    """
    Returns a list of input records (see module docstring).

    Args:
        input_dir:     read-only mount path (EUCAIM convention).
        input_format:  "dicom" | "nifti" | "auto".
        scratch_dir:   writable directory for DICOM→NIfTI conversion artefacts.
                       Created under tempfile.gettempdir() if not provided.
    """
    if not os.path.isdir(input_dir):
        raise NotADirectoryError(f"Input directory not found: {input_dir}")

    if scratch_dir is None:
        scratch_dir = tempfile.mkdtemp(prefix="prostai_input_")
    os.makedirs(scratch_dir, exist_ok=True)

    fmt = input_format.lower()
    records: List[Dict[str, Optional[str]]] = []

    if fmt in ("dicom", "auto"):
        for rec in _detect_dicom_studies(input_dir):
            case_id = f"{rec['subject_id']}_{rec['study_id']}_{rec['series_id']}"
            nifti_path = _convert_dicom_dir_to_nifti(rec["dicom_dir"], scratch_dir, case_id)
            if nifti_path is None:
                continue
            records.append(
                {
                    "case_id": case_id,
                    "subject_id": rec["subject_id"],
                    "study_id": rec["study_id"],
                    "nifti_path": nifti_path,
                    "source_dicom_dir": rec["dicom_dir"],
                }
            )

    if fmt in ("nifti", "auto") and not records:
        for rec in _detect_niftis(input_dir):
            records.append(
                {
                    "case_id": rec["subject_id"],
                    "subject_id": rec["subject_id"],
                    "study_id": rec["study_id"],
                    "nifti_path": rec["nifti_path"],
                    "source_dicom_dir": None,
                }
            )

    if not records:
        raise FileNotFoundError(
            f"No DICOM series or .nii.gz files found in {input_dir} (format={input_format})."
        )

    LOGGER.info("Discovered %d input case(s) in %s.", len(records), input_dir)
    return records
