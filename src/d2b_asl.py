from __future__ import annotations

import csv
import json
import logging
from io import StringIO
from itertools import chain
from pathlib import Path
from typing import TYPE_CHECKING

from d2b.hookspecs import hookimpl

if TYPE_CHECKING:
    from d2b.d2b import D2B, Acquisition


__version__ = "1.0.0"

ASL_CONTEXT_DESCRIPTION_PROPERTY = "aslContext"


@hookimpl
def pre_run_logs(logger: logging.Logger):
    logger.info(f"d2b-asl:version: {__version__}")


@hookimpl
def post_move(out_dir: Path, acquisitions: list[Acquisition], d2b: D2B):
    generate_context_files(out_dir, acquisitions, d2b.logger)


def generate_context_files(
    out_dir: Path,
    acquisitions: list[Acquisition],
    logger: logging.Logger,
):
    asl_acquisitions = find_asl_acquisitions(acquisitions)
    for acq in asl_acquisitions:
        logger.info(_msg_asl_found(acq))
        asl_context = AslContext(acq)
        try:
            asl_context.write_bids_tsv(out_dir)
        except ValueError as e:
            logger.warning(str(e))
            continue
        asl_context.write_bids_json(out_dir)


def find_asl_acquisitions(acquisitions: list[Acquisition]) -> list[Acquisition]:
    return [acq for acq in acquisitions if is_asl(acq)]


def is_asl(acquisition: Acquisition) -> bool:
    description = acquisition.description
    return description.data_type == "perf"


class AslContext:
    def __init__(self, acquisition: Acquisition):
        self.acquisition = acquisition

    @property
    def tsv_file(self) -> Path:
        dst_root = self.acquisition.dst_root_no_modality
        return dst_root.parent / f"{dst_root.stem}_aslcontext.tsv"

    @property
    def json_file(self) -> Path:
        dst_root = self.acquisition.dst_root_no_modality
        return dst_root.parent / f"{dst_root.stem}_aslcontext.json"

    @property
    def labels(self) -> list[str] | None:
        description = self.acquisition.description
        return description.data.get(ASL_CONTEXT_DESCRIPTION_PROPERTY)

    def tsv(self) -> StringIO:
        if self.labels is None:
            raise ValueError(_msg_asl_with_missing_labels(self.acquisition))

        f = StringIO()
        records = [{"volume_type": label} for label in self.labels]
        fieldnames = sorted(set(chain(*(r.keys() for r in records))))
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for r in records:
            writer.writerow(r)
        f.seek(0)
        return f

    def json(self) -> StringIO:
        f = StringIO()
        json.dump(generate_asl_context_sidecar_content(), f, indent=2)
        f.seek(0)
        return f

    def write_tsv(self, filename: str | Path) -> Path:
        out_file = Path(filename)
        out_file.write_text(self.tsv().read())
        return out_file

    def write_json(self, filename: str | Path) -> Path:
        out_file = Path(filename)
        out_file.write_text(self.json().read())
        return out_file

    def write_bids_tsv(self, dataset_dir: str | Path) -> Path:
        out_file = Path(dataset_dir) / self.tsv_file
        return self.write_tsv(out_file)

    def write_bids_json(self, dataset_dir: str | Path) -> Path:
        out_file = Path(dataset_dir) / self.json_file
        return self.write_json(out_file)


def generate_asl_context_sidecar_content():
    return {
        "volume_type": {
            "LongName": "Volume type",
            "Description": "Labels identifying the volume type of each volume in the corresponding *_asl.nii[.gz] file. Volume types are based on DICOM Tag (0018,9257) ASL Context.",  # noqa: E501
            "Levels": {
                "control": "The control image is acquired in the exact same way as the label image, except that the magnetization of the blood flowing into the imaging region has not been inverted.",  # noqa: E501
                "label": "The label image is acquired in the exact same way as the control image, except that the blood magnetization flowing into the imaging region has been inverted.",  # noqa: E501
                "m0scan": "The M0 image is a calibration image, used to estimate the equilibrium magnetization of blood.",  # noqa: E501
                "deltam": "The deltaM image is a perfusion-weighted image, obtained by the subtraction of control - label.",  # noqa: E501
                "cbf": "The cerebral blood flow (CBF) image is produced by dividing the deltaM by the M0, quantified into mL/100g/min (See also doi:10.1002/mrm.25197).",  # noqa: E501
            },
            "TermURL": "https://bids-specification.readthedocs.io/en/v1.6.0/04-modality-specific-files/01-magnetic-resonance-imaging-data.html#_aslcontexttsv",  # noqa: E501
        },
    }


def _msg_asl_found(acquisition: Acquisition):
    return (
        f"Found ASL acquisition associated with file [{acquisition.src_file}]. "
        "Writing aslcontext files."
    )


def _msg_asl_with_missing_labels(acquisition: Acquisition):
    return (
        f"Acquisition associated with file [{acquisition.src_file}] (matching "
        f"description at position [{acquisition.description.index}]) was "
        "determined to be an ASL acquisition, but has no "
        f"{ASL_CONTEXT_DESCRIPTION_PROPERTY!r} field. No "
        "'*_aslcontext.tsv' file will be generated for this acquisition."
    )
