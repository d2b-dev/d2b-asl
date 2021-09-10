# d2b-asl

Plugin for the d2b package to handle ASL data

[![PyPI Version](https://img.shields.io/pypi/v/d2b-asl.svg)](https://pypi.org/project/d2b-asl/)

## Installation

```bash
pip install d2b-asl
```

## User Guide

This package adds support for the `aslContext` field in the description objects located in the `d2b` config files. This field should be an array of strings, where each string is a volume type (as defined in the [BIDS specification here](https://bids-specification.readthedocs.io/en/v1.6.0/04-modality-specific-files/01-magnetic-resonance-imaging-data.html#_aslcontexttsv)). Specifically, this array should have the same number of entries as the described ASL acquisition has volumes (if there are 109 volumes in the acquisition which this description is describing, then `aslContext` should be an array of length 109).

For example, a config file describing an ASL acquisition might looks something like:

```json
{
  "descriptions": [
    {
      "dataType": "perf",
      "modalityLabel": "asl",
      "criteria": {
        "ProtocolName": "ep2d_pasl",
        "MagneticFieldStrength": 3,
        "MRAcquisitionType": "2D",
        "ImageType": [
          "ORIGINAL",
          "PRIMARY",
          "ASL",
          "NONE",
          "ND",
          "NORM",
          "FILTERED",
          "MOSAIC"
        ]
      },
      "sidecarChanges": {
        "ArterialSpinLabelingType": "PASL",
        "PostLabelingDelay": 1.8,
        "BackgroundSuppression": false,
        "M0Type": "Included",
        "TotalAcquiredPairs": 54,
        "AcquisitionVoxelSize": [3.5, 3.5, 4.5],
        "BolusCutOffFlag": true,
        "BolusCutOffDelayTime": 0.7,
        "BolusCutOffTechnique": "Q2TIPS",
        "PASLType": "PICORE"
      },
      "aslContext": [
        "m0scan",
        "control",
        "label",
        "control",
        "label",
        "control",
        "label",
        // full array omitted for readability ...
        "control",
        "label"
      ]
    }
  ]
}
```
