import argparse
import typing as t
from pathlib import Path

import pycldf
import openpyxl

from lexedata.types import Language, RowObject, CogSet
import lexedata.importer.cellparser as cell_parsers
from lexedata.importer.fromexcel import ExcelCognateParser
from lexedata.util import clean_cell_value, get_cell_comment


class CognateEditParser(ExcelCognateParser):
    def language_from_column(self, column: t.List[openpyxl.cell.Cell]) -> Language:
        data = [clean_cell_value(cell) for cell in column[: self.top - 1]]
        # Do we need to know language comments? – comment = get_cell_comment(column[0])
        return Language(
            {
                self.db.dataset["LanguageTable", "name"].name: data[0],
            }
        )

    def properties_from_row(
        self, row: t.List[openpyxl.cell.Cell]
    ) -> t.Optional[RowObject]:
        data = [clean_cell_value(cell) for cell in row[: self.left - 1]]
        properties: t.Dict[t.Optional[str], t.Any] = dict(zip(self.row_header, data))
        if not any(properties.values()):
            return None

        # delete all possible None entries coming from row_header
        cogset: t.Dict[str, t.Any] = {
            key: value for key, value in properties.items() if key is not None
        }

        while None in properties.keys():
            del properties[None]

        comments: t.List[str] = []
        for cell in row[: self.left - 1]:
            c = get_cell_comment(cell)
            if c is not None:
                comments.append(c)
        comment = "\t".join(comments).strip()
        cogset[self.db.dataset["CognatesetTable", "comment"].name] = comment
        return CogSet(cogset)


if __name__ == "__main__":

    parser = argparse.ArgumentParser(
        description="Load #cognate and #cognatesets from excel file into CLDF"
    )
    parser.add_argument(
        "cogsets",
        nargs="?",
        default="cognates.xlsx",
        help="Path to an Excel file containing cogsets and cognatejudgements (default: cognates.xlsx)",
    )
    parser.add_argument(
        "--metadata",
        type=Path,
        default="Wordlist-metadata.json",
        help="Path to the JSON metadata file describing the dataset (default: ./Wordlist-metadata.json)",
    )

    args = parser.parse_args()

    ws = openpyxl.load_workbook(args.cogsets).active

    dataset = pycldf.Dataset.from_metadata(args.metadata)

    # TODO the following lines of code would make a good template for the
    # import of cognate sets in fromexcel. Can we write a single function for
    # both use cases?

    row_header = []
    for (header,) in ws.iter_cols(
        min_row=1,
        max_row=1,
        max_col=len(dataset["CognatesetTable"].tableSchema.columns),
    ):
        column_name = header.value
        if column_name is None:
            column_name = dataset["CognatesetTable", "id"].name
        elif column_name == "CogSet":
            column_name = dataset["CognatesetTable", "id"].name
        try:
            column_name = dataset["CognatesetTable", column_name].name
        except KeyError:
            break
        row_header.append(column_name)

    excel_parser_cognate = CognateEditParser(
        dataset,
        None,
        top=2,
        # When the dataset has cognateset comments, that column is not a header
        # column, so this value is one higher than the actual number of header
        # columns, so actually correct for the 1-based indices. When there is
        # no comment column, we need to compensate for the 1-based Excel
        # indices.
        cellparser=cell_parsers.CellParserHyperlink(),
        row_header=row_header,
        check_for_language_match=[dataset["LanguageTable", "name"].name],
        check_for_match=[dataset["FormTable", "id"].name],
        check_for_row_match=[dataset["CognatesetTable", "id"].name],
    )

    # TODO: This often doesn't work if the dataset is not perfect before this
    # program is called. In particular, it doesn't work if there are errors in
    # the cognate sets or judgements, which will be reset in just a moment. How
    # else should we solve this?
    excel_parser_cognate.db.cache_dataset()
    excel_parser_cognate.db.drop_from_cache("CognatesetTable")
    excel_parser_cognate.db.drop_from_cache("CognateTable")
    excel_parser_cognate.parse_cells(ws)
    excel_parser_cognate.db.write_dataset_from_cache(
        ["CognateTable", "CognatesetTable"]
    )
