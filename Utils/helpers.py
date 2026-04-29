"""I/O helpers for the prostate zone segmentor.

Outputs per case (under <output_dir>/<subject_id>/<study_id>/):
    wg_binary.nii.gz, pz_binary.nii.gz, tz_binary.nii.gz
    wg_probs.nii.gz,  pz_probs.nii.gz,  tz_probs.nii.gz   (only if --save-probs)
    prostate_zones_seg.dcm                                (only if input was DICOM)

Plus a single <output_dir>/results.json index of all cases.
"""

import json
import logging
import os
from typing import Dict, List, Optional

import numpy as np
import SimpleITK as sitk

from Utils import ImageProcessor

LOGGER = logging.getLogger(__name__)


def _case_output_dir(output_dir: str, subject_id: str, study_id: str) -> str:
    path = os.path.join(output_dir, subject_id, study_id)
    os.makedirs(path, exist_ok=True)
    return path


def initial_processing(pats: dict, scratch_dir: str) -> dict:
    """Resamples + crops/pads each case for the WG nnU-Net stage.

    Writes the preprocessed volumes under <scratch_dir>/Dataset016_.../ImagesTs/.
    """
    pats_for_wg = {key: ImageProcessor.ImageProcessing(val) for key, val in pats.items()}

    out_dir = os.path.join(
        scratch_dir, "nnUNet_raw", "Dataset016_WgSegmentationPNetAndPicai", "ImagesTs"
    )
    os.makedirs(out_dir, exist_ok=True)
    for key, image in pats_for_wg.items():
        sitk.WriteImage(image, os.path.join(out_dir, f"ProstateWG_{key}_0000.nii.gz"))
    return pats_for_wg


class ImageProcessorClass:
    """Post-processes WG inference outputs and prepares cropped volumes for the zone stage."""

    def __init__(self, scratch_dir: str):
        self.scratch_dir = scratch_dir
        self.wg_paths_resampled: Dict[str, Dict[str, str]] = {}

    def process_images(
        self,
        pats_for_wg_inference: Dict[str, dict],
        pats_for_wg: Dict[str, sitk.Image],
        pats: Dict[str, sitk.Image],
        records_by_case: Dict[str, dict],
        output_dir: str,
        save_probs: bool,
    ) -> None:
        zone_input_dir = os.path.join(
            self.scratch_dir,
            "nnUNet_raw",
            "Dataset019_ProstateZonesSegmentationWgFilteredLessDilated",
            "ImagesTs",
        )
        os.makedirs(zone_input_dir, exist_ok=True)

        for key, val in pats_for_wg_inference.items():
            try:
                wg_binary = sitk.ReadImage(val["binary"])
                wg_binary = ImageProcessor.process_mask(wg_binary)
                wg_binary = ImageProcessor.remove_small_components(wg_binary)

                filtered = ImageProcessor.filter_ser(
                    pats_for_wg[key], ImageProcessor.mask_dilation(wg_binary)
                )

                # Resample WG mask back to the original input image grid.
                wg_resampled = sitk.Resample(
                    wg_binary, pats[key], sitk.Transform(), sitk.sitkNearestNeighbor
                )

                rec = records_by_case[key]
                case_out = _case_output_dir(output_dir, rec["subject_id"], rec["study_id"])
                wg_path = os.path.join(case_out, "wg_binary.nii.gz")
                sitk.WriteImage(wg_resampled, wg_path)

                paths = {"wg_binary": wg_path}

                if save_probs:
                    probs = np.load(val["probs"])["probabilities"][1]
                    wg_probs_img = sitk.GetImageFromArray(probs)
                    wg_probs_img.CopyInformation(wg_binary)
                    wg_probs_resampled = sitk.Resample(
                        wg_probs_img, pats[key], sitk.Transform(), sitk.sitkLinear
                    )
                    probs_path = os.path.join(case_out, "wg_probs.nii.gz")
                    sitk.WriteImage(wg_probs_resampled, probs_path)
                    paths["wg_probs"] = probs_path

                self.wg_paths_resampled[key] = paths

                # Stage 2 input: filtered T2 cropped by dilated WG mask.
                sitk.WriteImage(
                    filtered,
                    os.path.join(
                        zone_input_dir,
                        f"ProstateZonesFilteredLessDilated_ProstateZones_{key}_0000.nii.gz",
                    ),
                )
            except Exception as exc:
                LOGGER.error("WG post-processing failed for %s: %s", key, exc)

    def get_paths(self) -> Dict[str, Dict[str, str]]:
        return self.wg_paths_resampled


class ZoneProcessor:
    """Splits the multi-class zone mask into PZ/TZ binary masks resampled to original grid."""

    def __init__(self):
        self.zone_paths: Dict[str, Dict[str, str]] = {}

    def process_zones(
        self,
        pats_for_zones: Dict[str, dict],
        pats: Dict[str, sitk.Image],
        records_by_case: Dict[str, dict],
        output_dir: str,
        save_probs: bool,
    ) -> None:
        for key, val in pats_for_zones.items():
            try:
                zones = sitk.ReadImage(val["binary"])
                tz_binary, pz_binary = ImageProcessor.create_binary_masks(zones)
                tz_binary = ImageProcessor.process_mask(tz_binary)
                pz_binary = ImageProcessor.process_mask(pz_binary)
                tz_binary = ImageProcessor.remove_small_components(tz_binary)
                pz_binary = ImageProcessor.remove_small_components(pz_binary)

                rec = records_by_case[key]
                case_out = _case_output_dir(output_dir, rec["subject_id"], rec["study_id"])

                tz_path = os.path.join(case_out, "tz_binary.nii.gz")
                pz_path = os.path.join(case_out, "pz_binary.nii.gz")
                sitk.WriteImage(
                    sitk.Resample(tz_binary, pats[key], sitk.Transform(), sitk.sitkNearestNeighbor),
                    tz_path,
                )
                sitk.WriteImage(
                    sitk.Resample(pz_binary, pats[key], sitk.Transform(), sitk.sitkNearestNeighbor),
                    pz_path,
                )

                paths = {"tz_binary": tz_path, "pz_binary": pz_path}

                if save_probs:
                    probs = np.load(val["probs"])["probabilities"]
                    tz = sitk.GetImageFromArray(probs[1])
                    pz = sitk.GetImageFromArray(probs[2])
                    tz.CopyInformation(tz_binary)
                    pz.CopyInformation(pz_binary)
                    tz_probs_path = os.path.join(case_out, "tz_probs.nii.gz")
                    pz_probs_path = os.path.join(case_out, "pz_probs.nii.gz")
                    sitk.WriteImage(
                        sitk.Resample(tz, pats[key], sitk.Transform(), sitk.sitkLinear),
                        tz_probs_path,
                    )
                    sitk.WriteImage(
                        sitk.Resample(pz, pats[key], sitk.Transform(), sitk.sitkLinear),
                        pz_probs_path,
                    )
                    paths["tz_probs"] = tz_probs_path
                    paths["pz_probs"] = pz_probs_path

                self.zone_paths[key] = paths
            except Exception as exc:
                LOGGER.error("Zone post-processing failed for %s: %s", key, exc)

    def get_paths(self) -> Dict[str, Dict[str, str]]:
        return self.zone_paths


def fill_wg_with_zones(case_paths: Dict[str, str]) -> None:
    """Ensures WG mask is the union of WG ∪ PZ ∪ TZ to close any small gaps."""
    if not all(k in case_paths for k in ("wg_binary", "pz_binary", "tz_binary")):
        return
    wg = sitk.ReadImage(case_paths["wg_binary"])
    pz = sitk.ReadImage(case_paths["pz_binary"])
    tz = sitk.ReadImage(case_paths["tz_binary"])
    combined = sitk.Or(sitk.Or(wg, pz), tz)
    sitk.WriteImage(combined, case_paths["wg_binary"])


def write_results_index(
    output_dir: str,
    records_by_case: Dict[str, dict],
    case_paths: Dict[str, Dict[str, str]],
    failures: Dict[str, str],
) -> str:
    """Writes <output_dir>/results.json — single machine-readable index of the run."""
    cases: List[dict] = []
    for case_id, rec in records_by_case.items():
        entry: Dict[str, Optional[object]] = {
            "case_id": case_id,
            "subject_id": rec["subject_id"],
            "study_id": rec["study_id"],
            "source_dicom_dir": rec.get("source_dicom_dir"),
            "status": "failed" if case_id in failures else "ok",
        }
        if case_id in failures:
            entry["error"] = failures[case_id]
        else:
            paths = case_paths.get(case_id, {})
            entry["outputs"] = {
                k: os.path.relpath(v, output_dir) for k, v in paths.items()
            }
        cases.append(entry)

    index_path = os.path.join(output_dir, "results.json")
    with open(index_path, "w", encoding="utf-8") as f:
        json.dump({"cases": cases}, f, indent=2)
    return index_path


class DeleteRedundantfiles:
    """Removes nnU-Net intermediate files. Kept for backward compatibility — most
    intermediate files now live under WORK_DIR which is /tmp by default."""

    @staticmethod
    def clean_workspace(workdir: str) -> None:
        import shutil

        for sub in ("Dataset016_WgSegmentationPNetAndPicai", "Dataset019_ProstateZonesSegmentationWgFilteredLessDilated", "OutcomesWG", "OutcomesZones"):
            target = os.path.join(workdir, "nnUNet_raw", sub)
            if os.path.isdir(target):
                shutil.rmtree(target, ignore_errors=True)
