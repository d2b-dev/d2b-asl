# d2b-asl

Plugin for the d2b package to handle ASL data

[![PyPI Version](https://img.shields.io/pypi/v/d2b-asl.svg)](https://pypi.org/project/d2b-asl/)
[![Type Check](https://github.com/d2b-dev/d2b-asl/actions/workflows/type-check.yaml/badge.svg)](https://github.com/d2b-dev/d2b-asl/actions/workflows/type-check.yaml)
[![Code Style](https://github.com/d2b-dev/d2b-asl/actions/workflows/lint.yaml/badge.svg)](https://github.com/d2b-dev/d2b-asl/actions/workflows/lint.yaml)

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

## d2b-asl and array sidecar fields

There are two spots where you might be specifying arrays as field values in your d2b config files.

1. `aslContext` - This array should _ALWAYS_ have the same length as the number of volumes in your ASL data.

1. fields in `SidecarChanges` - These are fields like `RepetitionTimePreparation`, `PostLabelingDelay` etc. which may or may not need to be arrays. If they _are_ arrays, then these arrays should have length equal to the number of volumes in the files **_output_** by d2b.

Why are the lengths of the fields in item 2 potentially different from the lengths of `aslContext` in item 1? In the event that `aslContext` has "discard" values in its array, the number of volumes in the output ASL data will be different than the number of volumes in the input data.

The lengths of any of the arrays in `SidecarChanges` should take these discarded volumes into account. For example, suppose we have:

```json
{
  "aslContext": ["m0scan", "discard", "label", "control"]
}
```

then the `PostLabelingDelay` field would look like:

```json
{
  "SidecarChanges": {
    "PostLabelingDelay": [0, 1.8, 1.8]
  },
  "aslContext": ["m0scan", "discard", "label", "control"]
}
```

In general, the following relationship should hold:

```python
len_sidecar_changes_field = len(config.SidecarChanges["<array-field>"])
len_aslcontext = len(config.aslContext)
len_aslcontext_discard = len(list(filter(lambda v: v == "discard", config.aslContext)))

len_sidecar_changes_field == len_aslcontext - len_aslcontext_discard
```

## Understanding ASL-specific BIDS sidecar fields

So you a have ASL data and need to format it, great!

Here we try to unpack the most confusing parts of translating acquisition metadata into BIDS sidecar fields. We do this by considering 4 major classes of "acquisition configuration":

- PCASL + Separate M0
- PCASL + Included M0
- PASL + Separate M0
- PASL + Included M0

In each of the 4 scenarios we'll touch on:

- How to determine the following parameters:
  - `RepetitionTimePreparation`
  - `PostLabelingDelay`
  - `LabelingDuration`
  - `InversionTime`
- What the implications are with regard to array-like sidecar fields for ASL data.

As a historical/contextual note, it seems like the people who were/are involved in the creation of the ASL-specific portions of the BIDS specification have close ties (or are the same people) who work on the ASL tools included in FSL, and who created [https://asl-docs.readthedocs.io](https://asl-docs.readthedocs.io). As such, we'll use the same language found there (FSL + asl-docs), because many of the concepts intentions in those locations seem to have made their way into the BIDS spec.

> IMPORTANT: Any of the fields discussed here that can/should be of type `number[]`, should be arrays of length equal to the number of volumes in the associated acquisition, unless explicitly indicated otherwise.

### PCASL + Separate M0

If this is how you acquired your ASL data then congratulations, because this is probably the least confusing of the 4 scenarios.

- **`RepetitionTimePreparation`**

  **tl;dr**: Probably `number` (same as `RepetitionTime`)

  Unless you know that the TR varies (and how it varies) during the course of the ASL acquisition (in which case this field should be an array, see the note above) then this number can most likely be of type `number` (i.e. a single (scalar) value), and should probably match (be equal to) whatever is listed as the `RepetitionTime`

- **`PostLabelingDelay`**

  **tl;dr**: `number` (if single delay) or `number[]` (if multi-delay)

  If you have single-delay data, then this field can simply be a scalar (single value), namely the single post-label delay with which your data was acquired. This will likely (or at least hopefully likely) be recorded in the MRI protocol sheet somewhere, worst case: someone in your lab (the lab that collected the data) will know what it is/was.

  If you have multi-delay data, then this field should be of type `number[]` i.e. an array of numbers equal in length to the number of volumes in the ASL acquisition. Each number in the array should be the post-label delay used to acquire the volume at the corresponding index. (i.e. `sidecar.PostLabelingDelay[0]` is the delay used for the first volume, `sidecar.PostLabelingDelay[12]` is the delay used for the 13th volume, etc.)

- **`LabelingDuration`**

  **tl;dr**: Probably `number`

  Similar to `RepetitionTimePreparation`, this is (very) probably a single number unless your know and/or have good reason to be believe that it should be an array (in which case this field should be an array, see the note above). This value will most likely be listed in the MRI protocol sheet as: `label duration` or `bolus duration`.

- **`InversionTime`**

  **tl;dr**: `number`

  This should be whatever is listed in the DICOM header (or protocol sheet).

### PCASL + Included M0

- **`RepetitionTimePreparation`**

  **tl;dr**: Probably `number` (but _should_ be `number[]` - an array)

  First, we'll talk about what probably _should_ be provided for this field, then we'll talk about you'll likely be able to provide.

  Because of how the M0 images are acquired it's possible that the TR for the M0 volume(s) is(are) different (likely longer) than the TR for the rest of the "regular" ASL volumes. If this is the case _and_ you actually _know_ what the different TRs are, then this field should be an array (where length == num vols, yada yada ..., see the note above about arrays).

  It's possible that either: A) the TR for the M0 volume(s) is(are) known to be the same as for the rest of the volumes, or B) that you _suspect_ that the TRs are different, but you don't know what they are. In this case, either because it's right (A), or because it practical (B), this number will be of type `number` (i.e. a single scalar value) which equals (is the same as) the `RepetitionTime` field listed for this acquisition.

- **`PostLabelingDelay`**

  **tl;dr**: `number[]` (MUST be an array)

  In the previous section this field could have been a scalar or an array. In this case, it's no longer situation-dependent, **this field must be an array of `number[]`**.

  This is because, for the M0 volumes, (which are mixed in with the "regular" ASL volumes) the post-label delay is 0, so effectively we have a multi-delay timeseries with _at least_ 2 delays:

  1. the M0 delay (0), and
  1. the delay(s) that you collected the "regular" ASL volumes (one (single-delay) or more (multi-delay) values > 0)

- **`LabelingDuration`**

  **tl;dr**: `number[]` (MUST be an array)

  The same argument that applied to `PostLabelingDelay` (in this section, above) applies here, the only difference is that, realisitically, this will (in most cases) be an array of exactly two values: `0` and `[actual-label-duration-from-protocol-sheet]` (<- which is probably a single value)

- **`InversionTime`**

  **tl;dr**: `number`

  This should be whatever is listed in the DICOM header (or protocol sheet).

### PASL + Separate M0

- **`RepetitionTimePreparation`**

  **tl;dr**: Probably `number` (but _should_ be `number[]` - an array)

  See the discussion for `RepetitionTimePreparation` in the section [PCASL + Separate M0](#pcasl--separate-m0)

- **`PostLabelingDelay`**

  **tl;dr**: `number` (if single delay) or `number[]` (if multi-delay)

  This is where things start to get more complicated. Already, there is a potentially confusing mixture of terms ([described here](https://asl-docs.readthedocs.io/en/latest/analysis_guide.html#post-label-delay-s)), specifically, (**only for PASL**):

  ```text
  t_inversion (TI) = t_inflow (also, TI) = t_pld (as specified by BIDS)
  ```

  In the context of a (P)CASL (continuous) ASL acquisition, we talk about `label duration` and `post-label delay` (the sum of the two asl-docs calls the `inflow time`).

  ```text
  t_inflow = t_label + t_pld
  ```

  In the context of a PASL (pulsed) ASL acqusition, we talk about the `inversion time (TI)`, typically, for PASL, there aren't two "parts" to the inflow time, but instead we just have the inversion time:

  ```text
  t_inflow = t_inversion
  ```

  **However**, Since "inflow time" isn't an available BIDS sidecar field, the next best option might be `InversionTime` (an actual BIDS sidecar field), but there are two problems with using this field:

  1. this field already has a different non-ASL meaning/role, and
  1. this field cannot be an array (`number[]`), which is a requirement of whatever field we use in order to accommodate multi-inversion time (multi-delay) PASL fields

  Thus, to avoid adding yet another field the to the BIDS spec, the `PostLabelingDelay` field is used. As such, in the case of PASL:

  ```text
  t_inflow = t_inversion = t_pld
  ```

  So the "inversion time" (delay) used to collect your PASL data should be placed as the `PostLabelingDelay` field value, which a `number` (scalar) for single-inversion (single-delay) data, and a `number[]` (array) for "multi-inversion" (multi-delay) data.

- **`LabelingDuration`**

  **tl;dr**: Should **NOT** be present ... or `number`

  Strictly speaking, the `LabelingDuration` field is an invalid field for data with `ArterialSpinLabelingType == "PASL"`, as such, this field should not appear in the associated sidecar.

  However, if you are hoping to make use of the [ASLPrep](https://github.com/PennLINC/aslprep) BIDS app, this tool assumes the presence of a `LabelingDuration` field (until [issue 167](https://github.com/PennLINC/aslprep/issues/167) is resolved). In this case one can get around this issue by setting:

  ```text
  {
    // other fields ...

    "LabelingDuration": 0

    // ...
  }
  ```

  in the sidecar and specifying `--skip-bids-validation` as a flag.

- **`InversionTime`**

  **tl;dr**: `number`

  This should be whatever is listed in the DICOM header (or protocol sheet).

### PASL + Included M0

- **`RepetitionTimePreparation`**

  **tl;dr**: Probably `number` (but _should_ be `number[]` - an array)

  See the discussion for `RepetitionTimePreparation` in the section [PCASL + Separate M0](#pcasl--separate-m0)

- **`PostLabelingDelay`**

  **tl;dr**: `number[]`

  For the same reasons that `PostLabelingDelay` MUST be an array ([outline in this section](#pcasl--included-m0)), this field must _also_ be an arary.

  Regarding the interpretation/where to find these values see the discussion on `PostLabelingDelay` field in the [previous section](#pasl--separate-m0)

- **`LabelingDuration`**

  **tl;dr**: Should **NOT** be present ... or `number`

  Same reasoning as the [previous section](#pasl--separate-m0) with the same caveat/remark/hack regarding ASLPrep.

- **`InversionTime`**

  **tl;dr**: `number`

  This should be whatever is listed in the DICOM header (or protocol sheet).
