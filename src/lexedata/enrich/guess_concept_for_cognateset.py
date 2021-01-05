import typing as t
from pathlib import Path
from csvw.metadata import URITemplate
import pycldf
import networkx
from lexedata.util import load_clics

FormID = str
ConceptID = str
CognatesetID = str


def tqdm(iter, total=0):
    return iter


def load_concepts_by_form(
    dataset: pycldf.Dataset,
) -> t.Dict[FormID, t.Sequence[ConceptID]]:
    """Look up all concepts for each form, and return them as dictionary."""
    concepts_by_form_id = dict()
    c_f_id = dataset.column_names.forms.id
    c_f_concept = dataset.column_names.forms.parameterReference
    for form in tqdm(
        dataset["FormTable"],
        total=dataset["FormTable"].common_props.get("dc:extent"),
    ):
        concept = form.get(c_f_concept, [])
        concepts_by_form_id[form[c_f_id]] = (
            concept if isinstance(concept, list) == str else [concept]
        )
    return concepts_by_form_id


def concepts_to_concepticon(dataset: pycldf.Wordlist) -> t.Mapping[ConceptID, int]:
    concept_to_concepticon = {
        row[dataset.column_names.parameters.id]: row.get(
            dataset.column_names.parameters.concepticonReference
        )
        for row in tqdm(
            dataset["ParameterTable"],
            total=dataset["ParameterTable"].common_props.get("dc:extent"),
        )
    }
    return concept_to_concepticon


def central_concept(
    concepts: t.Counter[ConceptID], concepts_to_concepticon: t.Mapping[ConceptID, int]
):
    central_concepts = {}
    centralities = networkx.algorithms.centrality.betweenness_centrality(
        clics.subgraph({concepts_to_concepticon.get(c) for c in concepts} - {None})
    )

    def effective_centrality(cc):
        concept, count = cc
        return count * centralities.get(concepts_to_concepticon.get(concept), 1)

    concept, count = max(concepts.items(), key=effective_centrality)
    return concept


def reshape_dataset(
    dataset: pycldf.Wordlist, add_column: bool = True
) -> pycldf.Dataset:
    # check for existing cognateset table
    if dataset.column_names.cognatesets is None:
        # Create a Cognateset Table
        dataset.add_component("CognatesetTable")

    # add a concept column to the cognateset table
    if add_column:
        if dataset.column_names.cognatesets.parameterReference is None:
            dataset.add_columns("CognatesetTable", "Core_Concept_ID")
            c = dataset["CognatesetTable"].tableSchema.columns[-1]
            c.datatype = dataset["ParameterTable", "ID"].datatype
            c.propertyUrl = URITemplate(
                "http://cldf.clld.org/v1.0/terms.rdf#parameterReference"
            )
            fname = dataset.write_metadata()
            # Reload dataset with new column definitions
            dataset = pycldf.Wordlist.from_metadata(fname)
    return dataset


def add_central_concepts_to_cognateset_table(
    dataset: pycldf.Dataset,
    central_concept: t.Mapping[CognatesetID, ConceptID],
    add_column: bool = True,
    overwrite_existing: bool = True,
) -> pycldf.Dataset:
    dataset = reshape_dataset(dataset, add_column=add_column)
    c_core_concept = dataset.column_names.cognatesets.parameterReference
    if c_core_concept is None:
        raise ValueError(
            f"Dataset {dataset:} had no parameterReference column in a CognatesetTable"
            " and is thus not compatible with this script."
        )

    # write cognatesets with central concepts
    write_back = []
    for row in tqdm(
        dataset["CognatesetTable"],
        total=dataset["CognatesetTable"].common_props.get("dc:extent"),
    ):
        row[c_core_concept] = central_concept.get(
            row[dataset.column_names.cognatesets.id]
        )
        write_back.append(row)
    dataset.write(CognatesetTable=write_back)
    return dataset


def connected_concepts(
    dataset: pycldf.Wordlist,
) -> t.Mapping[CognatesetID, t.Counter[ConceptID]]:
    """For each cognate set it the data set, check which concepts it is connected to.

    >>>
    """
    concepts_by_form = load_concepts_by_form(dataset)
    cognatesets_to_concepts: t.DefaultDict[
        CognatesetID, t.Sequence[ConceptID]
    ] = t.DefaultDict(list)

    # Check whether cognate judgements live in the FormTable …
    c_cognateset = dataset.column_names.forms.cognatesetReference
    c_form = dataset.column_names.forms.id
    table = dataset["FormTable"]
    # … or in a separate CognateTable
    if c_cognateset is None:
        c_cognateset = dataset.column_names.cognates.cognatesetReference
        c_form = dataset.column_names.cognates.formReference
        table = dataset["CognateTable"]

    if c_cognateset is None:
        raise ValueError(
            f"Dataset {dataset:} had no cognatesetReference column in a CognateTable"
            " or a FormTable and is thus not compatible with this script."
        )

    for judgement in tqdm(
        table,
        total=table.common_props.get("dc:extent"),
    ):
        cognatesets_to_concepts[judgement[c_cognateset]].extend(
            concepts_by_form[judgement[c_form]]
        )
    return {
        cogset: t.Counter(concepts)
        for cogset, concepts in cognatesets_to_concepts.items()
    }


if __name__ == "__main__":
    import argparse
    from tqdm import tqdm

    parser = argparse.ArgumentParser()
    parser.add_argument(
        "wordlist",
        default="cldf-metadata.json",
        type=Path,
        help="The wordlist to add Concepticon links to",
    )
    parser.add_argument(
        "add_column",
        default=False,
        action="store_true",
        help="Activate to add a new column Core_Concept_ID to cognatesetTable",
    )
    parser.add_argument(
        "--overwrite_existing",
        action="store_true",
        default=False,
        help="Activate to overwrite existing Core_Concept_ID of cognatesets",
    )
    args = parser.parse_args()
    try:
        clics: t.Optional[networkx.Graph] = load_clics()
    except FileNotFoundError:
        clics = None

    dataset = pycldf.Wordlist.from_metadata(args.wordlist)

    concepts_of_cognateset: t.Mapping[
        CognatesetID, t.Counter[ConceptID]
    ] = connected_concepts(dataset)
    central: t.Mapping[str, str] = {}
    if clics and dataset.column_names.parameters.concepticonReference:
        concept_to_concepticon = concepts_to_concepticon(dataset)
        for cognateset, concepts in concepts_of_cognateset.items():
            central[cognateset] = central_concept(concepts, concept_to_concepticon)
    else:
        for cognateset, concepts in concepts_of_cognateset.items():
            central[cognateset] = central_concept(concepts, {})

    add_central_concepts_to_cognateset_table(
        dataset,
        central,
        add_column=args.add_column,
        overwrite_existing=args.overwrite_existing,
    )
