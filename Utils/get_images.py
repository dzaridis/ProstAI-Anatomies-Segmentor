"""
Discover input studies under an input directory and return structured records.

Layouts supported (auto-detected unless overridden by --input-format):

  1. EUCAIM CDM DICOM (preferred for production):
        <input_dir>/<patient>/<study>/<series>/*.dcm
        <input_dir>/index.json   (optional)

  2. NIfTI per patient (recommended NIfTI layout — matches the DICOM layout
     1:1 by series-folder name):
        <input_dir>/<patient>/t2_series.nii.gz                 (required)
        <input_dir>/<patient>/adc_series.nii.gz                (optional)
        <input_dir>/<patient>/dwi_series.nii.gz                (optional)

  3. NIfTI per patient/study (also accepted):
        <input_dir>/<patient>/<study>/t2_series.nii.gz         (required)
        <input_dir>/<patient>/<study>/adc_series.nii.gz        (optional)
        <input_dir>/<patient>/<study>/dwi_series.nii.gz        (optional)

  4. Flat NIfTI (legacy single-file smoke test, T2 only — no lesion):
        <input_dir>/<case_id>.nii.gz

Each returned record drives a single case (one T2 volume). When the matching
ADC and DWI sequences are also discovered, they are attached so that the
optional ProLesA-Net lesion stage can run.

    {
      "case_id":         str,           # used as filename stem in outputs
      "subject_id":      str,
      "study_id":        str,
      "nifti_path":      str,           # T2 NIfTI the segmentor will read
      "adc_path":        Optional[str], # set when an ADC sequence was found
      "dwi_path":        Optional[str], # set when a DWI sequence was found
      "source_dicom_dir": Optional[str] # T2 DICOM directory (DICOM input only)
    }
"""

import logging
import os
import re
import tempfile
from collections import defaultdict
from typing import Dict, List, Optional

import pydicom
from SimpleITK import (
    ImageSeriesReader,
    WriteImage,
    ImageSeriesReader_GetGDCMSeriesFileNames as GetGDCMSeriesFileNames,
)

LOGGER = logging.getLogger(__name__)

_T2_RE = re.compile(r"(?<![A-Za-z0-9])t2(?![0-9])", re.IGNORECASE)
_ADC_RE = re.compile(r"adc", re.IGNORECASE)
_DWI_RE = re.compile(r"(dwi|diff)", re.IGNORECASE)


def _classify(text: str) -> Optional[str]:
    if not text:
        return None
    if _ADC_RE.search(text):
        return "ADC"
    if _DWI_RE.search(text):
        return "DWI"
    if _T2_RE.search(text):
        return "T2"
    return None


def _read_dcm_series(dicom_files):
    reader = ImageSeriesReader()
    reader.SetFileNames(dicom_files)
    reader.MetaDataDictionaryArrayUpdateOn()
    reader.LoadPrivateTagsOn()
    return reader.Execute()


def _convert_dicom_dir_to_nifti(dicom_dir: str, scratch_dir: str, case_id: str) -> Optional[str]:
    files = GetGDCMSeriesFileNames(dicom_dir)
    if len(files) <= 1:
        LOGGER.warning("Skipping %s: needs >=2 DICOM files (multi-frame not supported).", dicom_dir)
        return None
    image = _read_dcm_series(files)
    out_path = os.path.join(scratch_dir, f"{case_id}.nii.gz")
    WriteImage(image, out_path)
    return out_path


def _series_modality(dicom_dir: str) -> Optional[str]:
    """Return 'T2' / 'ADC' / 'DWI' / None by inspecting the first DICOM file."""
    for fname in os.listdir(dicom_dir):
        if not fname.lower().endswith(".dcm"):
            continue
        try:
            ds = pydicom.dcmread(os.path.join(dicom_dir, fname), stop_before_pixels=True)
        except Exception:
            continue
        for tag in ("SeriesDescription", "ProtocolName", "SequenceName"):
            kind = _classify(getattr(ds, tag, None))
            if kind:
                return kind
        return _classify(os.path.basename(dicom_dir))
    return _classify(os.path.basename(dicom_dir))


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


def _nifti_case_id(rec: Dict[str, object]) -> str:
    """Compose a unique, filesystem-safe case_id for a NIfTI record.

    Flat layout (depth=0)            -> file stem
    Patient layout (depth=1)         -> patient id
    Patient/study layout (depth>=2)  -> "<patient>_<study>"
    """
    depth = int(rec.get("depth", 0))
    if depth == 0:
        return rec["stem"]
    if depth == 1:
        return rec["subject_id"]
    return f"{rec['subject_id']}_{rec['study_id']}"


def _detect_niftis(input_dir: str) -> List[Dict[str, str]]:
    """Walks input_dir; emits one record per .nii.gz file with subject/study attribution."""
    records = []
    for dirpath, _, files in os.walk(input_dir):
        rel_dir = os.path.relpath(dirpath, input_dir)
        parts = [] if rel_dir == "." else rel_dir.split(os.sep)
        for f in files:
            if not f.endswith(".nii.gz"):
                continue
            stem = f[: -len(".nii.gz")]
            if len(parts) == 0:
                # Flat: <input>/<case_id>.nii.gz  (legacy single-file smoke test)
                subject_id = study_id = stem
            elif len(parts) == 1:
                # Patient layout: <input>/<patient>/<seq>.nii.gz
                subject_id = study_id = parts[0]
            else:
                # Patient/study layout: <input>/<patient>/<study>/<seq>.nii.gz
                subject_id, study_id = parts[0], parts[1]
            records.append(
                {
                    "subject_id": subject_id,
                    "study_id": study_id,
                    "stem": stem,
                    "depth": len(parts),
                    "nifti_path": os.path.join(dirpath, f),
                }
            )
    return records


def _attach_aux_sequences_dicom(
    case_records: List[Dict[str, Optional[str]]],
    by_study: Dict[tuple, List[Dict[str, str]]],
    scratch_dir: str,
) -> None:
    """Scan study siblings and attach ADC/DWI nifti paths to T2 records (in-place)."""
    for case in case_records:
        siblings = by_study.get((case["subject_id"], case["study_id"]), [])
        for sib in siblings:
            if sib["dicom_dir"] == case.get("source_dicom_dir"):
                continue
            kind = _series_modality(sib["dicom_dir"])
            if kind not in ("ADC", "DWI"):
                continue
            key = "adc_path" if kind == "ADC" else "dwi_path"
            if case.get(key):
                continue
            aux_case_id = f"{case['case_id']}__{kind}"
            nii = _convert_dicom_dir_to_nifti(sib["dicom_dir"], scratch_dir, aux_case_id)
            if nii:
                case[key] = nii


def _attach_aux_sequences_nifti(
    case_records: List[Dict[str, Optional[str]]],
    by_study_files: Dict[tuple, List[Dict[str, str]]],
) -> None:
    """For each T2 record, look in the same folder for an ADC and a DWI .nii.gz."""
    for case in case_records:
        siblings = by_study_files.get((case["subject_id"], case["study_id"]), [])
        for sib in siblings:
            if sib["nifti_path"] == case["nifti_path"]:
                continue
            kind = _classify(sib["stem"])
            if kind == "ADC" and not case.get("adc_path"):
                case["adc_path"] = sib["nifti_path"]
            elif kind == "DWI" and not case.get("dwi_path"):
                case["dwi_path"] = sib["nifti_path"]


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
        scratch_dir:   writable directory for DICOM->NIfTI conversion artefacts.
                       Created under tempfile.gettempdir() if not provided.
    """
    if not os.path.isdir(input_dir):
        raise NotADirectoryError(f"Input directory not found: {input_dir}")

    if scratch_dir is None:
        scratch_dir = tempfile.mkdtemp(prefix="prostai_input_")
    os.makedirs(scratch_dir, exist_ok=True)

    fmt = input_format.lower()
    records: List[Dict[str, Optional[str]]] = []

    # --- DICOM path ------------------------------------------------------
    if fmt in ("dicom", "auto"):
        all_series = _detect_dicom_studies(input_dir)
        by_study: Dict[tuple, List[Dict[str, str]]] = defaultdict(list)
        for rec in all_series:
            by_study[(rec["subject_id"], rec["study_id"])].append(rec)

        # Within each study, classify each series; the T2 series drives a case.
        # If no T2 can be classified, fall back to "every series is a case"
        # (legacy behaviour) so single-series inputs still work.
        seen_t2 = False
        for rec in all_series:
            kind = _series_modality(rec["dicom_dir"])
            if kind != "T2":
                continue
            seen_t2 = True
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
                    "adc_path": None,
                    "dwi_path": None,
                    "source_dicom_dir": rec["dicom_dir"],
                }
            )

        if not seen_t2:
            for rec in all_series:
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
                        "adc_path": None,
                        "dwi_path": None,
                        "source_dicom_dir": rec["dicom_dir"],
                    }
                )
        else:
            _attach_aux_sequences_dicom(records, by_study, scratch_dir)

    # --- NIfTI path ------------------------------------------------------
    if fmt in ("nifti", "auto") and not records:
        all_files = _detect_niftis(input_dir)
        by_study_files: Dict[tuple, List[Dict[str, str]]] = defaultdict(list)
        for rec in all_files:
            by_study_files[(rec["subject_id"], rec["study_id"])].append(rec)

        seen_t2 = False
        for rec in all_files:
            if _classify(rec["stem"]) != "T2":
                continue
            seen_t2 = True
            records.append(
                {
                    "case_id": _nifti_case_id(rec),
                    "subject_id": rec["subject_id"],
                    "study_id": rec["study_id"],
                    "nifti_path": rec["nifti_path"],
                    "adc_path": None,
                    "dwi_path": None,
                    "source_dicom_dir": None,
                }
            )

        if not seen_t2:
            for rec in all_files:
                records.append(
                    {
                        "case_id": _nifti_case_id(rec),
                        "subject_id": rec["subject_id"],
                        "study_id": rec["study_id"],
                        "nifti_path": rec["nifti_path"],
                        "adc_path": None,
                        "dwi_path": None,
                        "source_dicom_dir": None,
                    }
                )
        else:
            _attach_aux_sequences_nifti(records, by_study_files)

    if not records:
        raise FileNotFoundError(
            f"No DICOM series or .nii.gz files found in {input_dir} (format={input_format})."
        )

    n_lesion = sum(1 for r in records if r.get("adc_path") and r.get("dwi_path"))
    LOGGER.info(
        "Discovered %d input case(s) in %s (%d with ADC+DWI for lesion).",
        len(records), input_dir, n_lesion,
    )
    return records
