"""nnU-Net v2 wrappers for whole-gland and zone segmentation.

Reads model location from MODEL_DIR env var (default: nnUnet_paths/) and writes
all intermediate predictions under WORK_DIR (default: /tmp/nnunet_workdir).
"""

import os
from abc import ABC, abstractmethod

MODEL_DIR = os.environ.get("MODEL_DIR", "nnUnet_paths")
WORK_DIR = os.environ.get("WORK_DIR", os.path.join(os.sep, "tmp", "nnunet_workdir"))

os.environ["nnUNet_raw"] = os.path.join(WORK_DIR, "nnUNet_raw")
os.environ["nnUNet_preprocessed"] = os.path.join(WORK_DIR, "nnUNet_preprocessed")
os.environ["nnUNet_results"] = os.path.join(MODEL_DIR, "nnUNet_results")

os.makedirs(os.environ["nnUNet_raw"], exist_ok=True)
os.makedirs(os.environ["nnUNet_preprocessed"], exist_ok=True)

from nnunetv2.paths import nnUNet_results, nnUNet_raw  # noqa: E402
from batchgenerators.utilities.file_and_folder_operations import join  # noqa: E402
from nnunetv2.inference.predict_from_raw_data import nnUNetPredictor  # noqa: E402
import torch  # noqa: E402


def _make_predictor() -> nnUNetPredictor:
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    return nnUNetPredictor(
        tile_step_size=0.5,
        use_gaussian=True,
        use_mirroring=True,
        perform_everything_on_gpu=device.type == "cuda",
        device=device,
        verbose=False,
        verbose_preprocessing=False,
        allow_tqdm=False,
    )


class BaseNNUnetModule(ABC):
    def __init__(self, input_path: str, output_path: str):
        self.input_path = input_path
        self.output_path = output_path
        self.predictor = _make_predictor()
        self.predictor.initialize_from_trained_model_folder(
            join(nnUNet_results, os.path.join(self.input_path, "nnUNetTrainer__nnUNetPlans__3d_fullres")),
            use_folds=(0,),
            checkpoint_name="checkpoint_final.pth",
        )

    @abstractmethod
    def prediction(self):
        ...

    @abstractmethod
    def return_paths(self, *args, **kwargs):
        ...


class WGNNUnet(BaseNNUnetModule):
    def prediction(self):
        self.predictor.predict_from_files(
            join(nnUNet_raw, os.path.join(self.input_path, "ImagesTs")),
            join(nnUNet_raw, self.output_path),
            save_probabilities=True,
            overwrite=True,
            num_processes_preprocessing=2,
            num_processes_segmentation_export=2,
            folder_with_segs_from_prev_stage=None,
            num_parts=1,
            part_id=0,
        )

    def return_paths(self, pats_for_wg: dict) -> dict:
        return {
            key: {
                "binary": os.path.join(join(nnUNet_raw, self.output_path), f"ProstateWG_{key}.nii.gz"),
                "probs": os.path.join(join(nnUNet_raw, self.output_path), f"ProstateWG_{key}.npz"),
            }
            for key in pats_for_wg
        }


class ZonesNNUnet(BaseNNUnetModule):
    def prediction(self):
        self.predictor.predict_from_files(
            join(nnUNet_raw, os.path.join(self.input_path, "ImagesTs")),
            join(nnUNet_raw, "OutcomesZones"),
            save_probabilities=True,
            overwrite=True,
            num_processes_preprocessing=2,
            num_processes_segmentation_export=2,
            folder_with_segs_from_prev_stage=None,
            num_parts=1,
            part_id=0,
        )

    def return_paths(self, pats_for_wg_inference: dict) -> dict:
        base = join(nnUNet_raw, "OutcomesZones")
        return {
            key: {
                "binary": os.path.join(base, f"ProstateZonesFilteredLessDilated_ProstateZones_{key}.nii.gz"),
                "probs": os.path.join(base, f"ProstateZonesFilteredLessDilated_ProstateZones_{key}.npz"),
            }
            for key in pats_for_wg_inference
        }
