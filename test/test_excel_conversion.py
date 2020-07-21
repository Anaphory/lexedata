import pytest
import shutil
import tempfile
from pathlib import Path

import pycldf
import openpyxl

from lexedata.importer.fromexcel import ExcelParser, ExcelCognateParser, MawetiGuaraniExcelParser, MawetiGuaraniExcelCognateParser
from lexedata.exporter.cognate_excel import ExcelWriter

#todo: these test must be adapted to new interface of fromexcel.py

@pytest.fixture
def excel_wordlist():
    return Path(__file__).parent / "data/excel/small.xlsx", Path(__file__).parent / "data/excel/small_cog.xlsx"


@pytest.fixture(params=[
        ("data/cldf/minimal/cldf-metadata.json", "data/cldf/minimal/db.sqlite"),
        ("data/cldf/smallmawetiguarani/cldf-metadata.json", "data/cldf/smallmawetiguarani/db.sqlite")])
def cldf_wordlist(request):
    return Path(__file__).parent / request.param[0], Path(__file__).parent / request.param[1]


@pytest.fixture
def empty_cldf_wordlist():
    # Copy the dataset metadata file to a temporary directory.
    original = Path(__file__).parent / "data/cldf/smallmawetiguarani/cldf-metadata.json"
    dirname = Path(tempfile.mkdtemp(prefix="lexedata-test"))
    target = dirname / original.name
    shutil.copyfile(original, target)
    # Create empty (because of the empty row list passed) csv files for the
    # dataset, one for each table, with only the appropriate headers in there.
    dataset = pycldf.Dataset.from_metadata(target)
    dataset.write(**{str(table.url): []
                     for table in dataset.tables})
    # Return the dataset API handle, which knows the metadata and tables.
    return dataset


@pytest.fixture
def filled_cldf_wordlist(cldf_wordlist):
    # Copy the dataset to a different temporary location, so that editing the
    # dataset will not change it.
    original = cldf_wordlist[0]
    dirname = Path(tempfile.mkdtemp(prefix="lexedata-test"))
    target = dirname / original.name
    databasefile = dirname / cldf_wordlist[1].name
    shutil.copyfile(original, target)
    dataset = pycldf.Dataset.from_metadata(target)
    for table in dataset.tables:
        link = Path(str(table.url))
        o = original.parent / link
        t = target.parent / link
        shutil.copyfile(o, t)
    link = dataset.bibpath.name
    o = original.parent / link
    t = target.parent / link
    shutil.copyfile(o, t)
    dataset.sources = pycldf.dataset.Sources.from_file(dataset.bibpath)
    return dataset, databasefile


def test_fromexcel_runs(excel_wordlist, empty_cldf_wordlist):
    # runs with default database, i.e. temporary file
    excel_parser_lexical = MawetiGuaraniExcelParser(empty_cldf_wordlist, excel_file=excel_wordlist[0])
    excel_parser_lexical.parse_cells()

    excel_parser_cognateset = MawetiGuaraniExcelCognateParser(empty_cldf_wordlist, excel_file=excel_wordlist[1])
    excel_parser_cognateset.parse_cells()


def test_toexcel_runs(filled_cldf_wordlist):
    writer = ExcelWriter(filled_cldf_wordlist[0], filled_cldf_wordlist[1])
    _, out_filename = tempfile.mkstemp(".xlsx", "cognates")
    writer.create_excel(out_filename)


def test_roundtrip(filled_cldf_wordlist):
    c_formReference = filled_cldf_wordlist[0]["CognateTable", "formReference"].name
    c_cogsetReference = filled_cldf_wordlist[0]["CognateTable", "cognatesetReference"].name
    old_judgements = {
        (row[c_formReference], row[c_cogsetReference])
        for row in filled_cldf_wordlist[0]["CognateTable"].iterdicts()}
    print(list(filled_cldf_wordlist[0]["FormTable"]))
    writer = ExcelWriter(filled_cldf_wordlist[0], filled_cldf_wordlist[1])
    print(list(filled_cldf_wordlist[0]["FormTable"]))
    _, out_filename = tempfile.mkstemp(".xlsx", "cognates")
    print(list(filled_cldf_wordlist[0]["FormTable"]))
    writer.create_excel(out_filename)

    # Reset the existing cognatesets and cognate judgements, to avoid
    # interference with the the data in the Excel file
    filled_cldf_wordlist[0]["CognateTable"].write([])
    filled_cldf_wordlist[0]["CognatesetTable"].write([])

    parser = ExcelCognateParser(filled_cldf_wordlist[0], excel_file=out_filename)
    parser.left = len(writer.header) + 1
    parser.parse_cells()
    # Really? Isn't there a shortcut to do this?
    parser.cldfdatabase.to_cldf(filled_cldf_wordlist[0].tablegroup._fname.parent)
    new_judgements = {
        (row[c_formReference], row[c_cogsetReference])
        for row in filled_cldf_wordlist[0]["CognateTable"].iterdicts()}

    assert new_judgements == old_judgements
