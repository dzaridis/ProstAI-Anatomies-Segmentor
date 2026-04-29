"""Load NIfTI inputs into a {case_id: SimpleITK.Image} dict."""

from typing import Dict, List

import SimpleITK as sitk


def load_nii_gz_files(records: List[dict]) -> Dict[str, sitk.Image]:
    """
    Args:
        records: list of dicts with keys "case_id" and "nifti_path"
                 (as produced by Utils.get_images.discover_inputs).
    Returns:
        {case_id: sitk.Image}
    """
    images: Dict[str, sitk.Image] = {}
    for rec in records:
        images[rec["case_id"]] = sitk.ReadImage(rec["nifti_path"])
    return images
