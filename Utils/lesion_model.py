"""ProLesA-Net lesion segmentation stage.

Runs a TensorFlow 2.11 SavedModel (`Checkpoint_320_nnconfs_Adam_CLR.tf`) on
T2 + ADC + DWI for each case, masked by the whole-gland (WG) prediction
already produced by the cascaded nnU-Net stage. The output is a binary
lesion mask resampled back to the original T2 grid.

The model is loaded lazily so that cases without ADC/DWI never pay the
TensorFlow import cost.
"""

from __future__ import annotations

import logging
import os
from typing import Dict, Optional

import numpy as np
import SimpleITK as sitk

from Utils import ImageProcessor
from Utils.wg_model import MinMaxNormalizer

LOGGER = logging.getLogger(__name__)

LESION_MODEL_DIR = os.environ.get(
    "LESION_MODEL_DIR",
    os.path.join(os.environ.get("MODEL_DIR", "nnUnet_paths"), "lesion", "Checkpoint_320_nnconfs_Adam_CLR.tf"),
)

LESION_TARGET_SPACING = (0.5, 0.5, 3.0)
LESION_TARGET_SIZE = (192, 192, 24)
LESION_DEFAULT_THRESHOLD = 0.1

_REQUIRED_SEQUENCES = ("T2", "ADC", "DWI")


def _prepare_stack(processed: Dict[str, sitk.Image]) -> np.ndarray:
    """Stack the three processed sequences into a (Z, H, W, 3) array (T2, ADC, DWI)."""
    arrays = [sitk.GetArrayFromImage(processed[seq]) for seq in _REQUIRED_SEQUENCES]
    return np.stack(arrays, axis=-1)


def _to_nifti(prediction: np.ndarray, reference: sitk.Image) -> sitk.Image:
    image = sitk.GetImageFromArray(prediction.squeeze())
    image.CopyInformation(reference)
    return image


class LesionSegmentor:
    """Lazy-loaded wrapper around the ProLesA-Net Keras SavedModel."""

    def __init__(self, model_path: str = LESION_MODEL_DIR, threshold: float = LESION_DEFAULT_THRESHOLD):
        self.model_path = model_path
        self.threshold = threshold
        self._model = None

    def _load(self):
        if self._model is None:
            if not os.path.isdir(self.model_path) and not os.path.isfile(self.model_path):
                raise FileNotFoundError(f"Lesion model not found at {self.model_path}")
            import tensorflow as tf  # heavy import — keep local

            tf.get_logger().setLevel("ERROR")
            LOGGER.info("Loading ProLesA-Net lesion model from %s", self.model_path)
            self._model = tf.keras.models.load_model(self.model_path, compile=False)
        return self._model

    def predict(
        self,
        t2: sitk.Image,
        adc: sitk.Image,
        dwi: sitk.Image,
        wg_binary: sitk.Image,
    ) -> sitk.Image:
        """Run the lesion model on a single case.

        Returns a binary lesion mask in the lesion-model spatial frame
        (spacing = LESION_TARGET_SPACING, size = LESION_TARGET_SIZE).
        Caller is responsible for resampling back to the desired output grid.
        """
        t2_proc = ImageProcessor.ImageProcessing(
            t2, spacing=LESION_TARGET_SPACING, target_size=LESION_TARGET_SIZE
        )
        adc_aligned = ImageProcessor.align_sequences(t2_proc, adc)
        dwi_aligned = ImageProcessor.align_sequences(t2_proc, dwi)
        adc_proc = ImageProcessor.resample(t2_proc, adc_aligned)
        dwi_proc = ImageProcessor.resample(t2_proc, dwi_aligned)
        wg_proc = ImageProcessor.resample(t2_proc, wg_binary)

        # SimpleITK's Mask filter is picky about 3D pixel types: cast images to
        # float32 and the mask to a binary uint8, otherwise it raises
        # "Pixel type: 16-bit unsigned integer is not supported in 3D".
        t2_f = sitk.Cast(t2_proc, sitk.sitkFloat32)
        adc_f = sitk.Cast(adc_proc, sitk.sitkFloat32)
        dwi_f = sitk.Cast(dwi_proc, sitk.sitkFloat32)
        wg_mask = sitk.Cast(sitk.Greater(wg_proc, 0), sitk.sitkUInt8)

        t2_masked = ImageProcessor.filter_ser(t2_f, wg_mask)
        adc_masked = ImageProcessor.filter_ser(adc_f, wg_mask)
        dwi_masked = ImageProcessor.filter_ser(dwi_f, wg_mask)

        normalizer = MinMaxNormalizer()
        sequences = {
            "T2": normalizer.normalize(t2_masked),
            "ADC": normalizer.normalize(adc_masked),
            "DWI": normalizer.normalize(dwi_masked),
        }

        stack = _prepare_stack(sequences)
        if stack.ndim == 4:
            stack = np.expand_dims(stack, axis=0)

        model = self._load()
        probs = model.predict(stack, verbose=0)
        binary_arr = (probs > self.threshold).astype(np.uint8)

        binary_image = _to_nifti(binary_arr.astype(np.uint8), sequences["T2"])
        probs_image = _to_nifti(probs.astype(np.float32), sequences["T2"])
        return binary_image, probs_image


def lesion_available(record: dict) -> bool:
    """True iff a record has the auxiliary ADC and DWI paths required for lesion."""
    return bool(record.get("adc_path")) and bool(record.get("dwi_path"))
