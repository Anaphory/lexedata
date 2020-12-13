from pathlib import Path
import tempfile
import shutil
import pytest
import pycldf

from lexedata.enrich.guess_concept_for_cognateset import ConceptGuesser
from lexedata.enrich.guess_concepticon import create_concepticon_for_concepts


@pytest.fixture(params=["data\cldf\smallmawetiguarani\cldf-metadata.json"])
def copy_wordlist_add_concepticons(request):
    original = Path(__file__).parent / request.param
    dirname = Path(tempfile.mkdtemp(prefix="lexedata-test"))
    target = dirname / original.name
    shutil.copyfile(original, target)
    dataset = pycldf.Dataset.from_metadata(original)
    for table in dataset.tables:
        link = Path(str(table.url))
        o = original.parent / link
        t = target.parent / link
        shutil.copyfile(o, t)
    dataset = pycldf.Dataset.from_metadata(target)
    create_concepticon_for_concepts(dataset)
    return target, dataset


def test_value_error_no_concepticonReferenc_for_concepts():
    with pytest.raises(ValueError):
        ConceptGuesser(
            pycldf.Dataset.from_metadata(
                "data/cldf/smallmawetiguarani/cldf-metadata.json"
            ),
            add_column=False,
        )


def test_value_error_no_parameterReference_for_cognateset(
    copy_wordlist_add_concepticons,
):
    target, dataset = copy_wordlist_add_concepticons
    concept_guesser = ConceptGuesser(dataset, add_column=False)
    with pytest.raises(ValueError):
        concept_guesser.add_central_concepts_to_cognateset_table()


def test_concepticon_id_of_concepts_correct(copy_wordlist_add_concepticons):
    target, dataset = copy_wordlist_add_concepticons
    c_concepticon = dataset["ParameterTable", "concepticonReference"].name
    concepticon_for_concepts = [str(row[c_concepticon]) for row in dataset["ParameterTable"]]
    assert concepticon_for_concepts == "1493,None,1498,None,492,None,1500,None,493".split(",")


def test_add_concepts_to_cognatesets_of_minimal_correct(copy_wordlist_add_concepticons):
    target, dataset = copy_wordlist_add_concepticons
    concept_guesser = ConceptGuesser(dataset)
    concept_guesser.add_central_concepts_to_cognateset_table()
    dataset = concept_guesser.dataset
    c_core_concept = dataset["CognatesetTable", "parameterReference"].name
    concepts_for_cognatesets = [
        row[c_core_concept] for row in dataset["CognatesetTable"]
    ]
    assert (
        concepts_for_cognatesets
        == "one,one,one,two,three,two,three,four,four,one,five".split(",")
    )
