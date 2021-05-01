# -*- coding: utf-8 -*-
import re
import typing as t
import urllib.parse
from pathlib import Path

import pycldf
import openpyxl as op

from lexedata import types
from lexedata.util import parse_segment_slice

WARNING = "\u26A0"

# ----------- Remark: Indices in excel are always 1-based. -----------

# TODO: Make comments on Languages, Cognatesets, and Judgements appear as notes
# in Excel.

# Type aliases, for clarity
CognatesetID = str


class ExcelWriter:
    """Class logic for cognateset Excel export."""

    header = [("ID", "CogSet")]  # Add columns here for other datasets.

    def __init__(
        self,
        dataset: pycldf.Dataset,
        database_url: t.Optional[str] = None,
        add_central_concepts: bool = False,
        singleton_cognate: bool = False,
    ):
        self.dataset = dataset
        self.add_concept = add_central_concepts
        self.singleton = singleton_cognate
        self.set_header()
        # set column for concept reference
        if self.add_concept:
            try:
                c_cogset_concept = self.dataset[
                    "CognatesetTable", "parameterReference"
                ].name
                self.header.insert(1, (c_cogset_concept, "Central_Concept"))
            except KeyError:
                self.header.insert(1, ("", "Central_Concept"))
        if database_url:
            self.URL_BASE = database_url
        else:
            self.URL_BASE = "https://example.org/{:s}"

    def set_header(self):
        c_id = self.dataset["CognatesetTable", "id"].name
        try:
            c_comment = self.dataset["CognatesetTable", "comment"].name
        except KeyError:
            c_comment = None
        self.header = []
        for column in self.dataset["CognatesetTable"].tableSchema.columns:
            if column.name == c_id:
                self.header.insert(0, (c_id, "CogSet"))
            elif column.name == c_comment:
                continue
            else:
                self.header.append((column.name, column.name))

    def create_excel(
        self,
        out: Path,
        size_sort: bool = False,
        language_order="name",
        status_update: t.Optional[str] = None,
    ) -> None:
        """Convert the initial CLDF into an Excel cognate view

        The Excel file has columns "CogSet", one column each mirroring the
        other cognateset metadata, and then one column per language.

        The rows contain cognate data. If a language has multiple reflexes in
        the same cognateset, these appear in different cells, one below the
        other.

        Parameters
        ==========
        out: The path of the Excel file to be written.

        size_sort: If true, cognatesets are ordered by the number of cognates
            corresponding to the cognateset

        language_order: column name, languages appear ordered by given column name from
            LanguageTable

        status_update: string, writen to status_column of singleton cognates.

        """
        wb = op.Workbook()
        ws: op.worksheet.worksheet.Worksheet = wb.active
        # if status update, add column to self.header
        if status_update and self.singleton:
            self.header.append(("", "Status_Column"))
        # Define the columns, i.e. languages and write to excel
        self.lan_dict: t.Dict[str, int] = {}
        excel_header = [name for cldf, name in self.header]
        c_name = self.dataset["LanguageTable", "name"].name
        c_id = self.dataset["LanguageTable", "id"].name
        if language_order:
            c_sort = self.dataset["LanguageTable", f"{language_order}"].name
            languages = sorted(
                self.dataset["LanguageTable"], key=lambda x: x[c_sort], reverse=False
            )
        else:
            languages = self.dataset["LanguageTable"]
        for col, lan in enumerate(languages, len(excel_header) + 1):
            self.lan_dict[lan[c_id]] = col
            excel_header.append(lan[c_name])
        ws.append(excel_header)

        # load all forms
        c_form_id = self.dataset["FormTable", "id"].name
        c_language = self.dataset["FormTable", "languageReference"].name
        all_forms = {f[c_form_id]: f for f in self.dataset["FormTable"]}

        # map form_id to id of associated concept
        c_form_concept_reference = self.dataset["FormTable", "parameterReference"].name
        concept_id_by_form_id = dict()
        for f in self.dataset["FormTable"]:
            concept = f[c_form_concept_reference]
            if isinstance(concept, str):
                concept_id_by_form_id[f[c_form_id]] = concept
            else:
                concept_id_by_form_id[f[c_form_id]] = concept[0]

        # load all cognates by cognateset id
        all_judgements: t.Dict[CognatesetID, t.List[types.CogSet]] = {}
        c_cognate_cognateset = self.dataset["CognateTable", "cognatesetReference"].name
        c_cognate_form = self.dataset["CognateTable", "formReference"].name
        for j in self.dataset["CognateTable"]:
            all_judgements.setdefault(j[c_cognate_cognateset], []).append(j)
        try:
            c_comment = self.dataset["CognatesetTable", "comment"].name
        except KeyError:
            c_comment = None
        c_cogset_id = self.dataset["CognatesetTable", "id"].name

        # Again, row_index 2 is indeed row 2, row 1 is header
        row_index = 1 + 1
        if size_sort:
            cogsets = sorted(
                self.dataset["CognatesetTable"],
                key=lambda x: len(all_judgements[x[c_cogset_id]]),
                reverse=True,
            )
        else:
            cogsets = self.dataset["CognatesetTable"]

        # iterate over all cogsets
        for cogset in cogsets:
            # possibly a cogset can appear without any judgment, if so ignore it
            if cogset[c_cogset_id] not in all_judgements:
                continue
            # write all forms of this cognateset to excel
            new_row_index = self.create_formcells_for_cogset(
                all_judgements[cogset[c_cogset_id]],
                ws,
                all_forms,
                row_index,
            )
            # write rows for cognatesets
            for row in range(row_index, new_row_index):
                for col, (db_name, header) in enumerate(self.header, 1):
                    # db_name is '' when add_central_concepts is activated
                    # and there is no concept column in cognateset table
                    # else read value from cognateset table
                    if header == "Central_Concept" and db_name == "":
                        # this is the concept associated to the first cognate in this cognateset
                        value = concept_id_by_form_id[
                            all_judgements[cogset[c_cogset_id]][0][c_cognate_form]
                        ]
                    else:
                        column = self.dataset["CognatesetTable", db_name]
                        if column.separator is None:
                            value = cogset[db_name]
                        else:
                            value = column.separator.join(
                                [str(v) for v in cogset[db_name]]
                            )
                    cell = ws.cell(row=row, column=col, value=value)
                    # Transfer the cognateset comment to the first Excel cell.
                    if c_comment and col == 1 and cogset.get(c_comment):
                        cell.comment = op.comments.Comment(
                            re.sub(f"-?{__package__}", "", cogset["Comment"]).strip(),
                            "lexedata.exporter",
                        )

            row_index = new_row_index
        # write remaining forms to singleton congatesets if switch is activated
        if self.singleton:
            # remove all forms that appear in judgements
            for k in all_judgements:
                for judgement in all_judgements[k]:
                    form_id = judgement[c_cognate_form]
                    try:
                        del all_forms[form_id]
                    except KeyError:
                        continue
            # create for remaining forms singleton cognatesets and write to file
            c_cogset_name = self.dataset["CognatesetTable", "name"].name
            try:
                c_cogset_concept = self.dataset[
                    "CognatesetTable", "parameterReference"
                ].name
            except KeyError:
                c_cogset_concept = None
            for i, form_id in enumerate(all_forms):
                # write form to file
                form = all_forms[form_id]
                self.create_formcell(
                    (form, dict()), ws, self.lan_dict[form[c_language]], row_index
                )
                # write singleton cognateset to excel
                for col, (db_name, header) in enumerate(self.header, 1):
                    if db_name == c_cogset_id:
                        value = f"X{i+1}_{form[c_language]}"
                    elif db_name == c_cogset_name:
                        value = concept_id_by_form_id[form_id]
                    # or the header was set to Central_Concept by switch add_concepts
                    # or cognateset dataset contains concept reference
                    elif header == "Central_Concept":
                        value = concept_id_by_form_id[form_id]
                    elif db_name == c_cogset_concept:
                        value = concept_id_by_form_id[form_id]
                    elif header == "Status_Column" and status_update is not None:
                        value = status_update
                    else:
                        value = ""
                    ws.cell(row=row_index, column=col, value=value)
                row_index += 1
        wb.save(filename=out)

    def create_formcells_for_cogset(
        self,
        cogset: types.CogSet,
        ws: op.worksheet.worksheet.Worksheet,
        all_forms: t.Dict[str, types.Form],
        row_index: int,
    ) -> int:
        """Writes all forms for given cognate set to Excel.

        Take all forms for a given cognate set as given by the database, create
        a hyperlink cell for each form, and write those into rows starting at
        row_index.

        Return the row number of the first empty row after this cognate set,
        which can then be filled by the following cognate set.

        """
        c_form = self.dataset["CognateTable", "formReference"].name
        c_language = self.dataset["FormTable", "languageReference"].name
        # Read the forms from the database and group them by language
        forms = t.DefaultDict[int, t.List[types.Form]](list)
        for judgement in cogset:
            form_id = judgement[c_form]
            form = all_forms[form_id]
            forms[self.lan_dict[form[c_language]]].append((form, judgement))

        if not forms:
            return row_index + 1

        # maximum of rows to be added
        maximum_cogset = max([len(c) for c in forms.values()])
        for column, cells in forms.items():
            for row, judgement in enumerate(cells, row_index):
                self.create_formcell(judgement, ws, column, row)
        # increase row_index and return
        row_index += maximum_cogset

        return row_index

    def create_formcell(
        self, judgement, ws: op.worksheet.worksheet.Worksheet, column: int, row: int
    ) -> None:
        """Fill the given cell with the form's data.

        In the cell described by ws, column, row, dump the data for the form:
        Write into the the form data, and supply a comment from the judgement
        if there is one.

        """
        cell_value = self.form_to_cell_value(judgement[0], judgement[1])
        form_cell = ws.cell(row=row, column=column, value=cell_value)
        c_id = self.dataset["FormTable", "id"].name
        c_comment = self.dataset["CognateTable", "comment"].name
        comment = judgement[1].get(c_comment, None)
        if comment:
            form_cell.comment = op.comments.Comment(comment, __package__)
        link = self.URL_BASE.format(urllib.parse.quote(judgement[0][c_id]))
        form_cell.hyperlink = link

    def form_to_cell_value(self, form: types.Form, meta: types.Judgement) -> str:
        """Build a string describing the form itself

        Provide the best transcription and all translations of the form strung
        together.

        k a w e n a t j a k a
        d i +dúpe
        +iíté+ k h ú
        tákeː+toː
        h o n _tiem_litimuleni
        hont i e m _litimuleni
        """
        segments = self.get_segments(form)
        if segments is None:
            transcription = form["Form"]
        else:
            transcription = ""
            # TODO: use CLDF property instead of column name
            if not meta.get("Segment_Slice"):
                meta["Segment_Slice"] = ["0:{:d}".format(len(segments))]
            # What if segments overlap or cross? Overlap shouldn't happen, but
            # we don't check here. Crossing might happen, but this
            # serialization cannot reflect it, so we enforce order, expecting
            # that an error message here will be more useful than silently
            # messing with data.
            included_segments = set(
                parse_segment_slice(meta["Segment_Slice"], enforce_ordered=True)
            )

            included = False
            for i, s in enumerate(segments):
                if included and i not in included_segments:
                    transcription += " }" + s
                    included = False
                elif not included and i in included_segments:
                    transcription += "{ " + s
                    included = True
                elif i in included_segments:
                    transcription += " " + s
                else:
                    transcription += s
            if included:
                transcription += " }"

            transcription = transcription.strip()
        translations = []

        suffix = ""
        try:
            c_comment = self.dataset["FormTable", "comment"].name
            if form.get(c_comment):
                suffix = f" {WARNING:}"
        except KeyError:
            pass

        # corresponding concepts
        # (multiple concepts) and others (single concept)
        c_concept = self.dataset["FormTable", "parameterReference"].name
        if isinstance(form[c_concept], list):
            for f in form[c_concept]:
                translations.append(f)
        else:
            translations.append(form[c_concept])
        return "{:} ‘{:}’{:}".format(transcription, ", ".join(translations), suffix)

    def get_segments(self, form):
        c_segments = self.dataset["FormTable", "Segments"].name
        return form[c_segments]


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="Create an Excel cognate view from a CLDF dataset"
    )
    parser.add_argument(
        "--metadata",
        type=Path,
        default="Wordlist-metadata.json",
        help="Path to the JSON metadata file describing the dataset (default: ./Wordlist-metadata.json)",
    )
    parser.add_argument(
        "excel",
        type=Path,
        help="File path for the generated cognate excel file.",
    )
    parser.add_argument(
        "--size-sort",
        action="store_true",
        default=False,
        help="List the biggest cognatesets first",
    )
    parser.add_argument(
        "--language-sort-column", help="A column name to sort languages by"
    )
    parser.add_argument(
        "--url-template",
        type=str,
        default="https://example.org/lexicon/{:})",
        help="A template string for URLs pointing to individual forms. For example, to"
        " point to lexibank, you would use https://lexibank.clld.org/values/{:}."
        " (default: https://example.org/lexicon/{:})",
    )
    parser.add_argument(
        "--add-concepts",
        action="store_true",
        default=False,
        help="Output the central concept associated with each cognateset",
    )
    parser.add_argument(
        "--add-singletons",
        action="store_true",
        default=False,
        help="Output all forms that don't belong to a cognateset. "
        "For each form, a singleton cognateset is created.",
    )
    parser.add_argument(
        "--status-update",
        type=str,
        default="automatic singleton",
        help="Text written to Status_Column. Set to 'None' for no status update. "
        "(default: automatic singleton)",
    )
    # TODO: Derive URL template from the "special:domain" property of the
    # wordlist, where it exists? So something like
    # 'https://{special:domain}/values/{{:}}'? It would work for Lexibank and
    # for LexiRumah, is it robust enough?
    args = parser.parse_args()
    if args.status_update == "None":
        args.status_update = None
    E = ExcelWriter(
        pycldf.Wordlist.from_metadata(args.metadata),
        database_url=args.url_template,
        add_central_concepts=args.add_concepts,
        singleton_cognate=args.add_singletons,
    )
    E.create_excel(
        args.excel,
        size_sort=args.size_sort,
        language_order=args.language_sort_column,
        status_update=args.status_update,
    )
