"""Validate (and, where possible, fix) a CLDF wordlist.

This script runs some more validators specific to (editing-friendly) CLDF
Wordlist data sets in addition to the validation implemented in the `pycldf`
core.

"""

from pathlib import Path
from clldutils.misc import log_or_raise
import logging
import pycldf
import typing as t

from lexedata.util import parse_segment_slice, cache_table


def check_segmentslice_separator(dataset, log=None):
    if dataset["FormTable", "segments"].separator != " ":
        log_or_raise(
            'FormTable segment separator must be " " (space) for downstream lexedata tools to work.',
            log=log,
        )
        return False
    return True


def check_cognate_table(dataset):
    """Check that the CognateTable makes sense.

    The cognate table MUST have an indication of forms, in a #formReference
    column, and cognate sets, in a #cognatesetReference column. It SHOULD have
    segment slices (#segmentSlice) and alignments (#alignment).

     - The segment slice must be a valid (1-based, inclusive) slice into the segments of the form
     - The alignment must match the segment slice applied to the segments of the form
     - The length of the alignment must match the lengths of other alignments of that cognate set

    Having no cognates is a valid choice for a dataset, so this function returns True if no CognateTable was found.

    """

    # First, load all forms that are referenced in the CognateTable

    try:
        cognatetable = dataset["CognateTable"]
    except KeyError:
        # Having no cognates is a valid choice for a dataset.
        return True

    try:
        c_form = dataset["CognateTable", "formReference"].name
    except KeyError:
        log_or_raise("CognateTable does not have a #formReference column.")
        # All further checks don't make sense, return early.
        return False

    try:
        c_cognateset = dataset["CognateTable", "cognatesetReference"].name
    except KeyError:
        log_or_raise("CognateTable does not have a #cognatesetReference column.")
        # All further checks don't make sense, return early.
        return False

    # The CLDF specifications state that foreign key references take precedence
    # over the implicit semantics of a `#xxxReference` column pointing to an
    # `#id` column, so we need to find forms by the stated foreign key
    # relationship.
    for foreign_key in cognatetable.tableSchema.foreignKeys:
        if foreign_key.columnReference == [c_form]:
            referenced_table = str(foreign_key.reference.resource)
            # A multi-column column reference for a single-column foreign key
            # makes no sense, so use tuple unpacking to extract the only
            # element from that list.
            (referenced_column,) = foreign_key.reference.columnReference
            if (
                not dataset[referenced_table].common_props["dc:conformsTo"]
                == "http://cldf.clld.org/v1.0/terms.rdf#FormTable"
            ):
                log_or_raise(
                    "CognateTable #formReference does not reference a FormTable."
                )
            break
    else:
        log_or_raise("CognateTable #formReference must be a foreign key.")
        # All further checks don't make sense, return early.
        return False

    try:
        c_sslice = dataset["CognateTable", "segmentSlice"].name
    except KeyError:
        log_or_raise("CognateTable does not have a #segmentSlice column.")
        c_sslice = None

    try:
        c_alignment = dataset["CognateTable", "alignment"].name
    except KeyError:
        log_or_raise("CognateTable does not have a #segmentSlice column.")
        c_alignment = None

    if c_sslice is None and c_alignment is None:
        # No additional data concerning the associations between forms and
        # cognate sets. That's sad, but valid.
        # All further checks don't make sense, return early.
        return True

    # Check whether each row is valid.
    all_judgements_okay = True
    forms = cache_table(
        dataset,
        columns={"segments": dataset[referenced_table, "segments"].name},
        table=referenced_table,
        index_column=referenced_column,
    )
    cognateset_alignment_lengths: t.DefaultDict[t.Set[int]] = t.DefaultDict(set)

    for f, j, judgement in dataset["CognateTable"].iterdicts(
        log=..., with_metadata=True
    ):
        form_segments = forms[judgement[c_form]]
        if c_sslice is not None:
            if not judgement[c_sslice]:
                log_or_raise("In {}, row {}: Empty segment slice".format(f, j))
                continue
            included_segments = list(parse_segment_slice(judgement[c_sslice]))
            if max(included_segments) >= len(form_segments):
                log_or_raise(
                    "In {}, row {}: Segment slice {} is invalid for segments {}".format(
                        f,
                        j,
                        judgement[c_sslice],
                        form_segments,
                    )
                )
                all_judgements_okay = False
        else:
            included_segments = range(len(form_segments))

        if c_alignment:
            # Length of alignment should match length of every other alignment in this cognate set.
            lengths = cognateset_alignment_lengths[judgement[c_cognateset]]
            alignment_length = len(judgement[c_alignment])
            if lengths and alignment_length not in lengths:
                log_or_raise(
                    "In {}, row {}: Alignment has length {}, other alignments of cognateset {} have length(s) {}".format(
                        f, j, alignment_length, judgement[c_cognateset], lengths
                    )
                )
                all_judgements_okay = False
            elif not lengths:
                lengths.add(alignment_length)

            # Alignment when gaps are removed should match segments. TODO:
            # Should we permit other gap characters? Where do we know them
            # from? TODO: To be more robust when segments are separated into
            # morphemes, not individual segments, compare alignment and
            # segments space-separated.
            without_gaps = " ".join([c for c in judgement[c_alignment] if c != "-"])
            actual_segments = " ".join(form_segments[i] for i in included_segments)
            if without_gaps.strip() != actual_segments.strip():
                log_or_raise(
                    "In {}, row {}: Referenced segments in form resolve to {}, while alignment contains segments {}.".format(
                        f, j, actual_segments, without_gaps
                    )
                )
                all_judgements_okay = False

    return all_judgements_okay


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--metadata",
        type=Path,
        default="Wordlist-metadata.json",
        help="Path to the JSON metadata file describing the dataset (default: ./Wordlist-metadata.json)",
    )
    args = parser.parse_args()

    dataset = pycldf.Dataset.from_metadata(args.metadata)

    dataset.auto_constraints()
    # Assume the dataset is conform with CLDF until proven otherwise.
    correct = True

    # Run basic CLDF validate
    correct &= dataset.validate(log=logging.Logger)

    # Check segment slice separator is space
    correct &= check_segmentslice_separator(dataset)

    # Check that the CognateTable makes sense
    correct &= check_cognate_table(dataset)

    # All ids should be primary keys

    # Which columns may contain separators?

    # no ID of a reference that contains separators may contain that separator

    #  Empty forms may exist, but only if there is no actual form for the concept and the language, and probably given some other constraints.
    #  All files should be in NFC normalized unicode
