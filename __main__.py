"""ProstAI Anatomies Segmentor — EUCAIM tool entrypoint.

Whole-gland (WG), peripheral-zone (PZ) and transition-zone (TZ) segmentation
from T2-weighted prostate MRI, using two cascaded nnU-Net v2 models.

Usage:
    docker run --rm --gpus all \\
        -v /path/to/input:/input:ro \\
        -v /path/to/output:/output \\
        harbor.eucaim.cancerimage.eu/processing-tools/prostate-zone-segmentor:<tag> \\
        --input /input --output /output

Run `--help` for the full flag reference.
"""

import argparse
import logging
import os
import signal
import sys
import tempfile
from typing import Dict


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="prostate-zone-segmentor",
        description="Prostate whole-gland and zonal segmentation from T2-weighted MRI.",
    )
    p.add_argument("--input", "-i", required=True,
                   help="Path to read-only input directory (DICOM series tree or .nii.gz files).")
    p.add_argument("--output", "-o", required=True,
                   help="Path to writable output directory.")
    p.add_argument("--input-format", choices=("auto", "dicom", "nifti"), default="auto",
                   help="Input layout (default: auto).")
    p.add_argument("--save-probs", action="store_true",
                   help="Also write probability maps (wg_probs/pz_probs/tz_probs).")
    seg_group = p.add_mutually_exclusive_group()
    seg_group.add_argument("--save-dicom-seg", dest="save_dicom_seg", action="store_true",
                           help="Emit a multi-segment DICOM-SEG when input is DICOM (default).")
    seg_group.add_argument("--no-save-dicom-seg", dest="save_dicom_seg", action="store_false",
                           help="Skip DICOM-SEG export even when input is DICOM.")
    p.set_defaults(save_dicom_seg=True)
    p.add_argument("--device", choices=("auto", "cuda", "cpu"), default="auto",
                   help="Inference device (default: auto-detect CUDA).")
    p.add_argument("--log-level", default="INFO",
                   choices=("DEBUG", "INFO", "WARNING", "ERROR"),
                   help="stdout log verbosity (default: INFO).")
    return p


def _configure_logging(level: str) -> None:
    logging.basicConfig(
        level=getattr(logging, level),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        stream=sys.stdout,
        force=True,
    )


def _install_signal_handlers() -> None:
    def _graceful_shutdown(signum, _frame):
        name = signal.Signals(signum).name
        logging.warning("Received %s — shutting down.", name)
        sys.exit(128 + signum)

    for s in (signal.SIGTERM, signal.SIGINT):
        signal.signal(s, _graceful_shutdown)


def _force_device(choice: str) -> None:
    if choice == "cpu":
        os.environ["CUDA_VISIBLE_DEVICES"] = ""
    elif choice == "cuda":
        os.environ.pop("CUDA_VISIBLE_DEVICES", None)


def main(argv=None) -> int:
    args = _build_parser().parse_args(argv)
    _configure_logging(args.log_level)
    _install_signal_handlers()
    _force_device(args.device)

    log = logging.getLogger("prostate-zone-segmentor")
    log.info("Input:  %s", args.input)
    log.info("Output: %s", args.output)
    log.info("Format: %s | save_probs=%s | save_dicom_seg=%s | device=%s",
             args.input_format, args.save_probs, args.save_dicom_seg, args.device)

    if not os.path.isdir(args.input):
        log.error("Input directory does not exist: %s", args.input)
        return 2
    os.makedirs(args.output, exist_ok=True)
    if not os.access(args.output, os.W_OK):
        log.error("Output directory is not writable: %s", args.output)
        return 2

    scratch_root = tempfile.mkdtemp(prefix="prostai_", dir="/tmp" if os.path.isdir("/tmp") else None)
    log.info("Scratch directory: %s", scratch_root)
    os.environ["WORK_DIR"] = scratch_root

    # Defer Utils imports until after env vars are set so nnU-Net picks up WORK_DIR.
    from Utils import InputCheck, helpers, segmentor_pipeline
    from Utils.get_images import discover_inputs

    failures: Dict[str, str] = {}
    try:
        records = discover_inputs(
            input_dir=args.input,
            input_format=args.input_format,
            scratch_dir=os.path.join(scratch_root, "input_nifti"),
        )
        records_by_case = {r["case_id"]: r for r in records}
        pats = InputCheck.load_nii_gz_files(records)

        case_paths = segmentor_pipeline.segmentor_pipeline_operation(
            pats=pats,
            records_by_case=records_by_case,
            output_dir=args.output,
            scratch_dir=scratch_root,
            save_probs=args.save_probs,
        )

        if args.save_dicom_seg:
            from Utils.nifti2dicomseg import nifti2dicomseg
            for case_id, paths in case_paths.items():
                rec = records_by_case[case_id]
                if not rec.get("source_dicom_dir"):
                    continue
                seg_dir = os.path.dirname(paths.get("wg_binary", ""))
                dcm_out = os.path.join(seg_dir, "prostate_zones_seg.dcm")
                try:
                    nifti2dicomseg(seg_dir, rec["source_dicom_dir"], output_path=dcm_out)
                    paths["dicom_seg"] = dcm_out
                    log.info("Wrote DICOM-SEG: %s", dcm_out)
                except Exception as exc:
                    log.error("DICOM-SEG export failed for %s: %s", case_id, exc)

        index_path = helpers.write_results_index(args.output, records_by_case, case_paths, failures)
        log.info("Wrote results index: %s", index_path)
        log.info("Done. Processed %d case(s), %d failure(s).",
                 len(records_by_case) - len(failures), len(failures))
        return 0 if not failures else 1

    except Exception as exc:
        log.exception("Fatal error: %s", exc)
        return 1
    finally:
        import shutil
        shutil.rmtree(scratch_root, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
