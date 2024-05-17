from __future__ import annotations

import argparse
import csv
import json
import logging
from dataclasses import dataclass
from io import StringIO
from itertools import chain
from pathlib import Path
from typing import Any
from typing import TYPE_CHECKING

import nibabel as nib
from d2b.hookspecs import hookimpl
from d2b.utils import first_nii

if TYPE_CHECKING:
    from d2b.d2b import D2B, Acquisition


__version__ = "2.0.1"

ASL_CONTEXT_DESCRIPTION_PROPERTY = "aslContext"
BIDS_LABELS = ["cbf", "control", "deltam", "label", "m0scan"]
ALLOWED_NON_BIDS_LABELS = ["discard"]


@hookimpl
def prepare_run_parser(parser: argparse.ArgumentParser):
    asl_group = parser.add_mutually_exclusive_group()
    asl_group.add_argument(
        "--include-aslcontext-json",
        dest="include_aslcontext_json",
        action="store_true",
        default=False,
        help="Include *_aslcontext.json files among the outputs generated "
        "by this command.",
    )
    asl_group.add_argument(
        "--no-include-aslcontext-json",
        dest="include_aslcontext_json",
        action="store_false",
        help="Do not include *_aslcontext.json files among the outputs "
        "generated by this command. This is the default. NOTE: This being "
        "the default may change in a future release.",
    )


@hookimpl
def pre_run_logs(logger: logging.Logger):
    logger.info(f"d2b-asl:version: {__version__}")


@hookimpl
def post_move(
    out_dir: Path,
    acquisitions: list[Acquisition],
    d2b: D2B,
    options: dict[str, Any],
):
    include_aslcontext_json: bool = options.get("include_aslcontext_json", False)
    generate_context_files(out_dir, acquisitions, include_aslcontext_json, d2b.logger)


def generate_context_files(
    out_dir: Path,
    acquisitions: list[Acquisition],
    include_aslcontext_json: bool,
    logger: logging.Logger,
):
    asl_acquisitions = find_asl_acquisitions(acquisitions)
    for acq in asl_acquisitions:
        logger.info(_msg_asl_found(acq))
        # create the context object
        aslcontext = Aslcontext.from_acquisition(acq)
        # find the nii file for this acquisition
        asl_file = find_asl_file(out_dir, acq)
        # validate the aslContext
        aslcontext.validate(asl_file)
        # write the tsv file
        aslcontext.write_bids_tsv(out_dir)
        # write the json file (if asked for)
        if include_aslcontext_json:
            aslcontext.write_bids_json(out_dir)
        # edit the asl data (if necessary)
        if aslcontext.should_discard_volumes():
            logger.info(_msg_will_discard_volumes(acq, aslcontext))
            discard_volumes(asl_file, aslcontext)


def find_asl_acquisitions(acquisitions: list[Acquisition]) -> list[Acquisition]:
    return [acq for acq in acquisitions if is_asl(acq)]


def is_asl(acquisition: Acquisition) -> bool:
    description = acquisition.description
    return description.modality_label == "_asl"


class Aslcontext:
    def __init__(self, labels: list[str], file_root: str | Path | None = None):
        self.labels = labels
        self.file_root = file_root

    @classmethod
    def from_acquisition(cls, acquisition: Acquisition):
        try:
            labels = acquisition.description.data[ASL_CONTEXT_DESCRIPTION_PROPERTY]
            file_root = acquisition.dst_root_no_modality
            return cls(labels, file_root)
        except KeyError as e:
            raise MissingAslcontextError(acquisition.description.index) from e

    @property
    def tsv_file(self) -> Path:
        if self.file_root is None:
            raise TypeError("Cannot write tsv file with NoneType file_root attribute.")
        dst_root = Path(self.file_root)
        return dst_root.parent / f"{dst_root.stem}_aslcontext.tsv"

    @property
    def json_file(self) -> Path:
        if self.file_root is None:
            raise TypeError("Cannot write json file with NoneType file_root attribute.")
        dst_root = Path(self.file_root)
        return dst_root.parent / f"{dst_root.stem}_aslcontext.json"

    def validate(self, asl_file: str | Path):
        img: nib.Nifti1Image = nib.load(asl_file)
        nvols, nlabels = img.header["dim"][4], len(self.labels)  # type: ignore
        if nvols != nlabels:
            raise AslContextConfigurationError(asl_file, nvols, nlabels)
        for label in self.labels:
            if not (label in BIDS_LABELS or label in ALLOWED_NON_BIDS_LABELS):
                raise InvalidAslcontextLabelError(label)

    def tagged_labels(self) -> list[TaggedLabel]:
        return [
            TaggedLabel(label not in ALLOWED_NON_BIDS_LABELS, label)
            for label in self.labels
        ]

    def should_discard_volumes(self) -> bool:
        return any(not t.is_bids for t in self.tagged_labels())

    def tsv(self) -> StringIO:
        f = StringIO()
        records = [{"volume_type": t.label} for t in self.tagged_labels() if t.is_bids]
        fieldnames = sorted(set(chain(*(r.keys() for r in records))))
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for r in records:
            writer.writerow(r)
        f.seek(0)
        return f

    def json(self) -> StringIO:
        f = StringIO()
        json.dump(generate_aslcontext_sidecar_content(), f, indent=2)
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


def discard_volumes(asl_file: str | Path, aslcontext: Aslcontext):
    """Discard volumes from the `.nii[.gz]` file associated with this acquisition."""
    keep_vols = [i for i, tl in enumerate(aslcontext.tagged_labels()) if tl.is_bids]
    if len(keep_vols) == len(aslcontext.tagged_labels()):
        # none of the volumes should be discarded, bail early
        return
    img: nib.Nifti1Image = nib.load(asl_file)
    data = img.get_data()
    _data = data[..., keep_vols]
    nib.save(img.__class__(_data, img.affine, img.header), asl_file)


def generate_aslcontext_sidecar_content():
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


def find_asl_file(dataset_dir: str | Path, acquisition: Acquisition) -> Path:
    asl_file = first_nii(dataset_dir / acquisition.dst_root)
    if asl_file is None:
        raise FileNotFoundError(
            "Could not find ASL NIfTI file for the acquisition with "
            f"dst_root [{acquisition.dst_root}]",
        )
    return asl_file


def _msg_asl_found(acquisition: Acquisition):
    return (
        f"Found ASL acquisition associated with file [{acquisition.src_file}]. "
        "Writing aslcontext files."
    )


def _msg_will_discard_volumes(acquisition: Acquisition, aslcontext: Aslcontext):
    non_bids_labels = [
        (i, t.label) for i, t in enumerate(aslcontext.tagged_labels()) if not t.is_bids
    ]
    reason_tpl = "volume at index [{i}] with label [{lab}]"
    reasons = list(map(lambda x: reason_tpl.format(i=x[0], lab=x[1]), non_bids_labels))
    reason_string = ",".join(reasons)
    return (
        f"ASL context for acqusition [{acquisition.dst_root}] has non-BIDS-compliant "
        f"aslContext labels. d2b-asl will remove volumes: {reason_string}"
    )


@dataclass
class TaggedLabel:
    is_bids: bool
    label: str


class MissingAslcontextError(ValueError):
    def __init__(self, description_index: int):
        self.description_index = description_index
        super().__init__(
            f"Description at index [{self.description_index}] is missing the "
            f"required property [{ASL_CONTEXT_DESCRIPTION_PROPERTY}]",
        )


class AslContextConfigurationError(ValueError):
    def __init__(self, asl_file: str | Path, nvols: int, nlabels: int):
        self.asl_file = asl_file
        self.nvols = nvols
        self.nlabels = nlabels
        super().__init__(
            f"File [{self.asl_file}] has a mismatch between the number of "
            f"volumes in the acquisition [{self.nvols}] and the number of "
            f"volume_type labels [{self.nlabels}] in the associated description",
        )


class InvalidAslcontextLabelError(ValueError):
    def __init__(self, label: str):
        self.label = label
        super().__init__(
            f"Unknown aslcontext label [{self.label}]. BIDS-compliant "
            f"labels are: {BIDS_LABELS!r}, d2b-asl also allows for the usage "
            f"of {ALLOWED_NON_BIDS_LABELS!r}",
        )
