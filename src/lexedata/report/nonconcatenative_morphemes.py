import typing as t
from pathlib import Path

import pycldf

from lexedata.util import parse_segment_slices


def segment_to_cognateset(dataset: pycldf.Dataset, cognatesets: t.Iterable):
    # required fields
    c_cognate_cognateset = dataset.column_names.cognates.cognatesetReference
    c_form_segments = dataset.column_names.forms.segments
    c_form_id = dataset.column_names.forms.id
    c_cognate_form = dataset.column_names.cognates.formReference

    forms = {f[c_form_id]: f for f in dataset["FormTable"]}
    cognateset_cache: t.Dict[t.Optional[str], int] = {
        cognateset["ID"]: c
        for c, cognateset in enumerate(dataset["CognatesetTable"], 1)
        if cognateset["ID"] in cognatesets
    }
    cognateset_cache[None] = 0

    which_segment_belongs_to_which_cognateset: t.Dict[str, t.List[t.Set[str]]] = {}
    for j in dataset["CognateTable"]:
        if j[c_cognate_form] in forms and j[c_cognate_cognateset] in cognateset_cache:
            form = forms[j[c_cognate_form]]
            if j[c_cognate_form] not in which_segment_belongs_to_which_cognateset:
                which_segment_belongs_to_which_cognateset[j[c_cognate_form]] = [
                    set() for _ in form[c_form_segments]
                ]
            segments_judged = parse_segment_slices(
                segments=form[c_form_segments], judgement=j
            )
            for s in segments_judged:
                try:
                    which_segment_belongs_to_which_cognateset[j[c_cognate_form]][s].add(
                        j[c_cognate_cognateset]
                    )
                except IndexError:
                    print(
                        f"WARNING: In judgement {j}, segment slice point outside valid range 0:{len(form[c_form_segments])}."
                    )
                    continue
    return which_segment_belongs_to_which_cognateset


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="List segments that indicate non-concatenative morphology "
    )
    parser.add_argument(
        "--metadata",
        type=Path,
        default="Wordlist-metadata.json",
        help="Path to the JSON metadata file describing the dataset (default: ./Wordlist-metadata.json)",
    )
    parser.add_argument(
        "--cognatesets",
        type=str,
        nargs="*",
        default=[],
        help="",
    )
    args = parser.parse_args()
    segment_to_cognateset(
        dataset=pycldf.Dataset.from_metadata(args.metadata),
        cognatesets=args.cognatesets,
    )
