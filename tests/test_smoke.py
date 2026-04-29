"""Smoke tests — exercise CLI plumbing without invoking the GPU model.

Heavier integration tests would need the model weights and a GPU and live in
a separate (offline) test suite.
"""

import os
import subprocess
import sys
import tempfile

import numpy as np
import SimpleITK as sitk


def test_help_runs():
    result = subprocess.run(
        [sys.executable, "__main__.py", "--help"],
        cwd=os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0
    assert "--input" in result.stdout
    assert "--output" in result.stdout


def test_discover_inputs_nifti():
    from Utils.get_images import discover_inputs

    with tempfile.TemporaryDirectory() as tmp:
        arr = np.zeros((4, 4, 4), dtype=np.float32)
        img = sitk.GetImageFromArray(arr)
        sitk.WriteImage(img, os.path.join(tmp, "case42.nii.gz"))

        records = discover_inputs(tmp, input_format="nifti")
        assert len(records) == 1
        assert records[0]["case_id"] == "case42"
        assert records[0]["source_dicom_dir"] is None
