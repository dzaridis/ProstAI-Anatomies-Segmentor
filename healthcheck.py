"""Lightweight liveness probe for the EUCAIM HEALTHCHECK directive.

The container is considered healthy if the model directory is readable and the
WORK_DIR is writable. For long batch runs you can extend this to check a
heartbeat file modified by the main process.
"""

import os
import sys


def is_healthy() -> bool:
    model_dir = os.environ.get("MODEL_DIR", "/opt/models")
    work_dir = os.environ.get("WORK_DIR", "/tmp/nnunet_workdir")
    if not os.path.isdir(model_dir):
        return False
    if not os.path.isdir(work_dir) or not os.access(work_dir, os.W_OK):
        return False
    return True


if __name__ == "__main__":
    sys.exit(0 if is_healthy() else 1)
