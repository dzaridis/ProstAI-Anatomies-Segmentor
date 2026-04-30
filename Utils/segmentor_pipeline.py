"""End-to-end prostate whole-gland + zonal + lesion segmentation pipeline."""

import logging
import os
import warnings
from typing import Dict

import SimpleITK as sitk

from Utils import helpers, nnUnet_call

warnings.filterwarnings("ignore")
LOGGER = logging.getLogger(__name__)


def segmentor_pipeline_operation(
    pats: Dict[str, sitk.Image],
    records_by_case: Dict[str, dict],
    output_dir: str,
    scratch_dir: str,
    save_probs: bool = False,
    save_lesion: bool = True,
    lesion_threshold: float = 0.1,
) -> Dict[str, Dict[str, str]]:
    """Run the full pipeline for the given cases.

    Returns a {case_id: {output_name: output_path}} dictionary of produced files.
    """
    seg = Segmentor(scratch_dir=scratch_dir)
    seg.wg_model(pats)
    seg.preparation_zones(pats, records_by_case, output_dir, save_probs)
    seg.zones_model()
    seg.post_process_zones(pats, records_by_case, output_dir, save_probs)

    case_paths: Dict[str, Dict[str, str]] = {}
    for case_id in pats:
        merged = {}
        merged.update(seg.wg_paths.get(case_id, {}))
        merged.update(seg.zone_paths.get(case_id, {}))
        case_paths[case_id] = merged
        helpers.fill_wg_with_zones(merged)

    if save_lesion:
        lesion_paths = run_lesion_stage(
            pats=pats,
            records_by_case=records_by_case,
            case_paths=case_paths,
            output_dir=output_dir,
            save_probs=save_probs,
            threshold=lesion_threshold,
        )
        for case_id, paths in lesion_paths.items():
            case_paths.setdefault(case_id, {}).update(paths)

    return case_paths


def run_lesion_stage(
    pats: Dict[str, sitk.Image],
    records_by_case: Dict[str, dict],
    case_paths: Dict[str, Dict[str, str]],
    output_dir: str,
    save_probs: bool,
    threshold: float,
) -> Dict[str, Dict[str, str]]:
    """Apply the ProLesA-Net lesion model to every case that has ADC + DWI."""
    from Utils.lesion_model import LesionSegmentor, lesion_available

    eligible = [cid for cid, rec in records_by_case.items() if lesion_available(rec)]
    if not eligible:
        LOGGER.info("Lesion stage skipped: no case has both ADC and DWI sequences.")
        return {}

    LOGGER.info("Running ProLesA-Net lesion stage on %d case(s).", len(eligible))
    lesion = LesionSegmentor(threshold=threshold)
    out: Dict[str, Dict[str, str]] = {}

    for case_id in eligible:
        rec = records_by_case[case_id]
        wg_path = case_paths.get(case_id, {}).get("wg_binary")
        if not wg_path or not os.path.isfile(wg_path):
            LOGGER.warning("Lesion skipped for %s: missing WG mask.", case_id)
            continue
        try:
            adc = sitk.ReadImage(rec["adc_path"])
            dwi = sitk.ReadImage(rec["dwi_path"])
            wg_binary = sitk.ReadImage(wg_path)

            binary_img, probs_img = lesion.predict(
                t2=pats[case_id], adc=adc, dwi=dwi, wg_binary=wg_binary,
            )

            binary_resampled = sitk.Resample(
                binary_img, pats[case_id], sitk.Transform(), sitk.sitkNearestNeighbor
            )
            case_out = helpers.case_output_dir(output_dir, rec["subject_id"], rec["study_id"])
            lesion_path = os.path.join(case_out, "lesion_binary.nii.gz")
            sitk.WriteImage(binary_resampled, lesion_path)
            paths = {"lesion_binary": lesion_path}

            if save_probs:
                probs_resampled = sitk.Resample(
                    probs_img, pats[case_id], sitk.Transform(), sitk.sitkLinear
                )
                probs_path = os.path.join(case_out, "lesion_probs.nii.gz")
                sitk.WriteImage(probs_resampled, probs_path)
                paths["lesion_probs"] = probs_path

            out[case_id] = paths
        except Exception as exc:
            LOGGER.error("Lesion segmentation failed for %s: %s", case_id, exc)

    return out


class Segmentor:
    def __init__(self, scratch_dir: str):
        self.scratch_dir = scratch_dir
        self.pats_for_wg: Dict[str, sitk.Image] = {}
        self.pats_for_wg_inference: Dict[str, dict] = {}
        self.pats_for_zones: Dict[str, dict] = {}
        self.wg_paths: Dict[str, Dict[str, str]] = {}
        self.zone_paths: Dict[str, Dict[str, str]] = {}

    def wg_model(self, pats: Dict[str, sitk.Image]) -> None:
        self.pats_for_wg = helpers.initial_processing(pats, self.scratch_dir)
        wg_nn = nnUnet_call.WGNNUnet(
            input_path="Dataset016_WgSegmentationPNetAndPicai",
            output_path="OutcomesWG",
        )
        wg_nn.prediction()
        self.pats_for_wg_inference = wg_nn.return_paths(pats_for_wg=self.pats_for_wg)

    def preparation_zones(
        self,
        pats: Dict[str, sitk.Image],
        records_by_case: Dict[str, dict],
        output_dir: str,
        save_probs: bool,
    ) -> None:
        proc = helpers.ImageProcessorClass(scratch_dir=self.scratch_dir)
        proc.process_images(
            self.pats_for_wg_inference,
            self.pats_for_wg,
            pats,
            records_by_case,
            output_dir,
            save_probs,
        )
        self.wg_paths = proc.get_paths()

    def zones_model(self) -> None:
        zones_nn = nnUnet_call.ZonesNNUnet(
            input_path="Dataset019_ProstateZonesSegmentationWgFilteredLessDilated",
            output_path="OutcomesZones",
        )
        zones_nn.prediction()
        self.pats_for_zones = zones_nn.return_paths(pats_for_wg_inference=self.pats_for_wg_inference)

    def post_process_zones(
        self,
        pats: Dict[str, sitk.Image],
        records_by_case: Dict[str, dict],
        output_dir: str,
        save_probs: bool,
    ) -> None:
        proc = helpers.ZoneProcessor()
        proc.process_zones(self.pats_for_zones, pats, records_by_case, output_dir, save_probs)
        self.zone_paths = proc.get_paths()
