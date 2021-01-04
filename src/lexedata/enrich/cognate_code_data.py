"""Similarity code tentative cognates in a word list and align them"""

import csv
import hashlib
import argparse
import typing as t
from pathlib import Path

import pycldf
import pyclts
import segments
import cldfbench
import cldfcatalog

import lingpy
import lingpy.compare.partial

clts_path = cldfcatalog.Config.from_file().get_clone("clts")
clts = cldfbench.catalogs.CLTS(clts_path)
bipa = clts.api.bipa

tokenizer = segments.Tokenizer()


def sha1(path):
    return hashlib.sha1(str(path).encode("utf-8")).hexdigest()[:12]


def clean_segments(segment_string: t.List[str]) -> t.Iterable[pyclts.models.Symbol]:
    """Reduce the row's segments to not contain empty morphemes.

    This function removes all unknown sound segments (/0/) from the segments
    string it is passed, and removes empty morphemes by collapsing subsequent
    morpheme boundary markers (_#◦+→←) into one.

    >>> segments = "+ _ t a + 0 + a t"
    >>> c = clean_segments(segments)
    >>> [str(s) for s in c]
    ['t', 'a', '+', 'a', 't']

    """
    segments = [bipa[x] for x in segment_string]
    segments.insert(0, bipa["#"])
    segments.append(bipa["#"])
    for s in range(len(segments) - 1, 0, -1):
        if not pyclts.models.is_valid_sound(segments[s - 1], bipa):
            if isinstance(segments[s - 1], pyclts.models.Marker) and isinstance(
                segments[s], pyclts.models.Marker
            ):
                del segments[s - 1]
            if isinstance(segments[s - 1], pyclts.models.UnknownSound):
                del segments[s - 1]
            continue
    return segments[1:-1]


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--metadata",
        nargs="?",
        type=Path,
        default="Wordlist-metadata.json",
        help="Path to the metadata.json. The metadata file describes the dataset. Default: ./Wordlist-metadata.json",
    )
    parser.add_argument(
        "--output-file",
        "-o",
        type=Path,
        help="File path for the generated output file.",
    )
    parser.add_argument(
        "--soundclass",
        default="sca",
        choices=["sca", "dolgo", "asjp", "art"],
        help="Sound class model to use. Default: sca",
    )
    parser.add_argument(
        "--threshold",
        default=0.55,
        type=float,
        help="Cognate clustering threshold value. Default: 0.55",
    )
    parser.add_argument(
        "--cluster-method",
        default="infomap",
        help="Cognate clustering method name. Valid options"
        " are, dependent on your LingPy version, {'upgma',"
        " 'single', 'complete', 'mcl', 'infomap'}."
        " (default: infomap)",
    )
    parser.add_argument(
        "--gop",
        default=-2,
        type=float,
        help="Gap opening penalty for the clustering" "procedure. (default: -2)",
    )
    parser.add_argument(
        "--mode",
        default="overlap",
        choices=["global", "local", "overlap", "dialign"],
        help="Select the mode for the alignment analysis." "(default: overlap)",
    )
    parser.add_argument(
        "--ratio",
        default=1.5,
        type=float,
        help="Ratio of language-pair specific vs. general"
        " scores in the LexStat algorithm. (default: 1.5)",
    )
    parser.add_argument(
        "--initial-threshold",
        default=0.7,
        type=float,
        help="Threshold value for the initial pairs used to"
        "bootstrap the calculation. (default: 0.7)",
    )
    args = parser.parse_args()

    dataset = pycldf.Wordlist.from_metadata(args.wordlist)

    def filter(row: t.Dict[str, t.Any]) -> bool:
        row["tokens"] = [
            str(x)
            for x in clean_segments(row[dataset.column_names.forms.segments.lower()])
        ]
        row["tokens"] = ["+" if x == "_" else x for x in row["tokens"]]
        # TODO: Find the official LingPy way to consider word boundaries to
        # also be morpheme boundaries – just adding them in
        # `partial_cluster(sep=...+'_')` did not work, and why isn't it the
        # default anyway?
        row["doculect"] = row[dataset.column_names.forms.languageReference.lower()]
        row["concept"] = row[dataset.column_names.forms.parameterReference.lower()]
        return row["segments"] and row["concept"]

    assert (
        dataset.column_names.forms.segments is not None
    ), "Dataset must have a CLDF #segments column."

    lex = lingpy.compare.partial.Partial.from_cldf(
        args.wordlist,
        filter=filter,
        columns=["doculect", "concept", "tokens"],
        model=lingpy.data.model.Model(args.soundclass),
        check=True,
    )

    if args.ratio != 1.5:
        if args.ratio == float("inf"):
            ratio_pair = (1, 0)
            ratio_str = "-inf"
        if args.ratio == int(args.ratio) >= 0:
            r = int(args.ratio)
            ratio_pair = (r, 1)
            ratio_str = "-{:d}".format(r)
        elif args.ratio > 0:
            ratio_pair = (args.ratio, 1)
            ratio_str = "-" + str(args.ratio)
        else:
            raise ValueError("LexStat ratio must be in [0, ∞]")
    else:
        ratio_pair = (3, 2)
        ratio_str = ""
    if args.initial_threshold != 0.7:
        ratio_str += "-t{:02d}".format(int(args.initial_threshold * 100))
    try:
        scorers_etc = lingpy.compare.lexstat.LexStat(
            filename="lexstats-{:}-{:s}{:s}.tsv".format(
                sha1(args.wordlist), args.soundclass, ratio_str
            )
        )
        lex.scorer = scorers_etc.scorer
        lex.cscorer = scorers_etc.cscorer
        lex.bscorer = scorers_etc.bscorer
    except (OSError, ValueError):
        lex.get_scorer(runs=10000, ratio=ratio_pair, threshold=args.initial_threshold)
        lex.output(
            "tsv",
            filename="lexstats-{:}-{:s}{:s}".format(
                sha1(args.wordlist), args.soundclass, ratio_str
            ),
            ignore=[],
        )
    # For some purposes it is useful to have monolithic cognate classes.
    lex.cluster(
        method="lexstat",
        threshold=args.threshold,
        ref="cogid",
        cluster_method=args.cluster_method,
        verbose=True,
        override=True,
        gop=args.gop,
        mode=args.mode,
    )
    # But actually, in most cases partial cognates are much more useful.
    lex.partial_cluster(
        method="lexstat",
        threshold=args.threshold,
        cluster_method=args.cluster_method,
        ref="partialcognateids",
        override=True,
        verbose=True,
        gop=args.gop,
        mode=args.mode,
    )
    lex.output("tsv", filename="auto-clusters")
    alm = lingpy.Alignments(lex, ref="partialcognateids", fuzzy=True)
    alm.align(method="progressive")
    alm.output("tsv", filename=args.output, ignore="all", prettify=False)

    try:
        dataset.add_component("CognateTable")
    except ValueError:
        ...
    try:
        dataset.add_component("CognatesetTable")
    except ValueError:
        ...

    read_back = csv.DictReader(open(args.output + ".tsv"), delimiter="\t")
    cognatesets = {}
    judgements = []
    i = 1
    for line in read_back:
        partial = line["PARTIALCOGNATEIDS"].split()
        alignment = line["ALIGNMENT"].split(" + ")
        slice_start = 0
        for cs, alm in zip(partial, alignment):
            cognatesets.setdefault(cs, {"ID": cs})
            length = len(alm.split())
            judgements.append(
                {
                    "ID": i,
                    "Form_ID": line["ID"],
                    "Cognateset_ID": cs,
                    "Segment_Slice": [
                        "{:d}:{:d}".format(slice_start, slice_start + length)
                    ],
                    "Alignment": alm.split(),
                    "Source": ["LexStat"],
                }
            )
            i += 1
            slice_start += length
    dataset.write(CognatesetTable=cognatesets.values())
    dataset.write(CognateTable=judgements)
