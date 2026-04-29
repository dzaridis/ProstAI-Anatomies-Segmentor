"""End-to-end prostate whole-gland + zonal segmentation pipeline."""

import logging
import os
import warnings
from typing import Dict, List

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
    return case_paths


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
