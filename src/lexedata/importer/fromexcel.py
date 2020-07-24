# -*- coding: utf-8 -*-

import os
import re
import warnings
import typing as t
from pathlib import Path
from tempfile import mkstemp

import pycldf
import openpyxl
import sqlalchemy
import sqlalchemy.ext.automap as automap

from lexedata.database.database import create_db_session, new_id, string_to_id
from lexedata.importer.cellparser import CellParser, MawetiGuaraniLexicalParser, \
    MawetiGuaraniCognateParser, CellParserHyperlink, CellParserLexical, get_cell_comment
import lexedata.importer.exceptions as ex
from lexedata.cldf.automapped import (
    SQLAlchemyWordlist, Language, Source, Form, Concept, CogSet, Reference)

# Remark: excel uses 1-based indices


# Adapt warnings – TODO: Probably the `logging` package would be better for
# this job than `warnings`.
def formatwarning(
        message: str, category: t.Type[Warning], filename: str, lineno: int,
        line: t.Optional[str] = None
) -> str:
    # ignore everything except the message
    return str(message) + '\n'


warnings.formatwarning = formatwarning


class ObjectNotFoundWarning(UserWarning):
    pass


class MultipleCandidatesWarning(UserWarning):
    pass


MissingHandler = t.Callable[
    ["ExcelParser", sqlalchemy.ext.automap.AutomapBase, t.Optional[str]],
    bool]


class ExcelParser(SQLAlchemyWordlist):

    def error(self, db_object: sqlalchemy.ext.automap.AutomapBase,
              cell: t.Optional[str] = None) -> bool:
        try:
            rep = db_object.cldf_name
        except AttributeError:
            try:
                rep = db_object.cldf_id
            except AttributeError:
                rep = repr(db_object)
        raise ObjectNotFoundWarning(
            f"Failed to find object {rep:} {cell:} in the database")

    def warn(self, db_object: sqlalchemy.ext.automap.AutomapBase,
             cell: t.Optional[str] = None) -> bool:
        try:
            rep = db_object.cldf_name
        except AttributeError:
            try:
                rep = db_object.cldf_id
            except AttributeError:
                rep = repr(db_object)
        warnings.warn(
            f"Failed to find object {rep:} in the database. Skipped. In cell: {cell:}.",
            ObjectNotFoundWarning)
        return False

    def warn_and_create(
            self, db_object: sqlalchemy.ext.automap.AutomapBase,
            cell: t.Optional[str] = None) -> bool:
        try:
            rep = db_object.cldf_name
        except AttributeError:
            try:
                rep = db_object.cldf_id
            except AttributeError:
                rep = repr(db_object)
        warnings.warn(
            f"Failed to find object {rep:}in the database. Added. Object of cell: {cell:}",
            ObjectNotFoundWarning)
        self.session.add(db_object)
        return True

    def create(self, db_object: sqlalchemy.ext.automap.AutomapBase,
               cell: t.Optional[str] = None) -> bool:
        self.session.add(db_object)
        return True

    def ignore(self, db_object: sqlalchemy.ext.automap.AutomapBase,
               cell: t.Optional[str] = None) -> bool:
        return False

    def __init__(self, output_dataset: pycldf.Dataset, excel_file: str,
                 top: int = 2, left: int = 2,
                 check_for_match: t.List[str] = ["cldf_id"],
                 check_for_row_match: t.List[str] = ["cldf_name"],
                 on_language_not_found: MissingHandler = create,
                 on_row_not_found: MissingHandler = create,
                 on_form_not_found: MissingHandler = create,
                 **kwargs) -> None:
        super().__init__(output_dataset, **kwargs)
        self.cell_parser: CellParser = CellParserLexical()
        self.top = top
        self.left = left
        self.check_for_match = check_for_match
        self.check_for_row_match = check_for_row_match
        self.on_language_not_found = on_language_not_found
        self.on_row_not_found = on_row_not_found
        self.on_form_not_found = on_form_not_found

        # creates self.sheets containing a list of all excel sheets, that will be parsed
        self.set_up_sheets(excel_file)

        class Sources(t.DefaultDict[str, Source]):
            def __missing__(inner_self, key: str) -> Source:
                source: t.Optional[Source] = self.session.query(
                    self.Source).filter(self.Source.id == key).one_or_none()
                if source is None:
                    source = self.Source(id=key, genre='misc',
                                         author='', editor='')
                    self.session.add(source)
                inner_self.__setitem__(key, source)
                return source

        self.sources = Sources()
        self.RowObject = self.Concept

    def set_up_sheets(self, fname: str) -> None:
        self.sheets = [openpyxl.load_workbook(filename=fname).worksheets[0]]

    def language_from_column(
            self, column: t.List[openpyxl.cell.Cell]
    ) -> t.Dict[str, t.Any]:
        data = [(cell.value or '').strip() for cell in column[:self.top - 1]]
        comment = get_cell_comment(column[0])
        return {
            "cldf_name": data[0],
            "cldf_comment": comment
        }

    def properties_from_row(
            self, row: t.List[openpyxl.cell.Cell]
    ) -> t.Dict[str, t.Any]:
        data = [(cell.value or '').strip() for cell in row[:self.left - 1]]
        comment = get_cell_comment(row[0])
        return {
            "cldf_name": data[0],
            "cldf_comment": comment
        }

    def init_lan(self) -> t.Dict[str, t.Any]:
        lan_dict: t.Dict[str, Language] = {}
        lan_iter: t.Iterable[t.List[openpyxl.cell.Cell]] = self.sheets[0].iter_cols(
            min_row=1, max_row=self.top - 1, min_col=self.left)
        # iterate over language columns
        for lan_col in lan_iter:
            if not any([(cell.value or '').strip() for cell in lan_col]):
                # Skip empty languages
                continue
            language_properties = self.language_from_column(lan_col)
            language = self.session.query(self.Language).filter(
                self.Language.cldf_name == language_properties["cldf_name"]
            ).one_or_none()
            if language is None:
                id = new_id(language_properties["cldf_name"], self.Language, self.session)
                language = self.Language(cldf_id=id, **language_properties)
                self.on_language_not_found(self, language, lan_col[0].coordinate)
            lan_dict[lan_col[0].column] = language

        return lan_dict

    def create_form_with_sources(
            self: "ExcelParser",
            row_object,
            sources: t.List[t.Tuple[Source, t.Optional[str]]] = [],
            **properties: t.Any) -> t.Tuple[Form, t.Sequence[Reference]]:

        form_id = new_id(
            "{:}_{:}".format(properties["language"].cldf_id, row_object.cldf_id),
            self.Form, self.session)

        form = self.Form(cldf_id=form_id, **properties)
        references = [
            self.Reference(
                form=form,
                source=source,
                context=context)
            for source, context in sources]
        return form, references

    def associate(self, form: Form, row: t.Union[Concept, CogSet]) -> None:
        try:
            form.parameter
            form.parameter = row
        except AttributeError:
            form.parameters.append(row)
        except KeyError:
            # This seems to be how SQLAlchemy signals the wrong object type
            tp = type(row)
            raise TypeError(
                f"Form {form:} expected a concept association, but got {tp:}.")

    def parse_cells(self) -> None:
        languages = self.init_lan()
        row_object: t.Optional[t.Union[Concept, CogSet]] = None
        for sheet in self.sheets:
            form_iter: t.Iterable[t.List[openpyxl.cell.Cell]] = sheet.iter_rows(
                min_row=self.top, min_col=self.left)
            row_iter: t.Iterable[t.List[openpyxl.cell.Cell]] = sheet.iter_rows(
                min_row=self.top, max_col=self.left - 1)
            for row_header, row_forms in zip(row_iter, form_iter):
                # Parse the row header, creating or retrieving the associated row
                # object (i.e. a concept or a cognateset)
                properties = self.properties_from_row(row_header)
                if not properties:
                    # Keep the old row_object from the previous line
                    assert row_object
                else:
                    similar = self.session.query(self.RowObject).filter(
                        *[getattr(self.RowObject, key) == properties[key]
                          for key in dir(self.RowObject)
                          if key in self.check_for_row_match
                          if type(properties[key]) != list]).all()

                    if len(similar) == 0:
                        row_id = new_id(
                            properties.pop("cldf_id", properties.get("cldf_name", "")),
                            self.RowObject, self.session)
                        row_object = self.RowObject(cldf_id=row_id, **properties)
                        if not self.on_row_not_found(
                                self, row_object, row_header[0].coordinate):
                            continue
                    elif len(similar) >= 1:
                        if len(similar) > 1:
                            warnings.warn(
                                f"Found more than one match for {properties:}")
                        row_object = similar[0]

                # Parse the row, cell by cell
                for f_cell in row_forms:
                    try:
                        this_lan = languages[f_cell.column]
                    except KeyError:
                        continue

                    # Parse the cell, which results (potentially) in multiple forms
                    for form_cell in self.cell_parser.parse(
                            f_cell, language=this_lan):
                        candidates_forms = self.session.query(self.Form).filter(
                            self.Form.language == this_lan)
                        if "cldf_value" in self.check_for_match:
                            forms = []
                            for this_form in candidates_forms:
                                given_cldf_values = form_cell["cldf_value"].split("_")
                                candidate_cldf_values = this_form.cldf_value.split("_")
                                while "-" in given_cldf_values:
                                    index = given_cldf_values.index("-")
                                    given_cldf_values.pop(index)
                                    candidate_cldf_values.pop(index)
                                if given_cldf_values == candidate_cldf_values:
                                    forms.append(this_form)
                        else:
                            forms = candidates_forms.query(self.Form).filter(
                                [getattr(self.Form, key) == form_cell[key] for key in dir(self.Form)
                                 if key in self.check_for_match
                                 if not isinstance(form_cell[key], list)]).all()
                        sources = [(self.sources[k], c or None)
                                   for k, c in form_cell.pop("sources", [])]
                        if "sources" in self.check_for_match:
                            for c in range(len(forms) - 1, -1, -1):
                                s = set(reference.source for reference in
                                        self.session.query(self.Reference).filter(
                                            self.Reference.form == forms[c]))
                                sources_only = {src[0] for src in sources}
                                if not sources_only & s:
                                    warnings.warn("Closest matching form {:} had sources {:} instead of {:}".format(
                                        forms[0].cldf_id,
                                        {src.id for src in s},
                                        {src.id for src in sources_only}))
                                    break
                        if len(forms) == 0:
                            form, references = self.create_form_with_sources(
                                row_object, sources=sources, **form_cell)

                            if not self.on_form_not_found(self, form, f_cell.coordinate):
                                try:
                                    self.session.delete(form)
                                except (sqlalchemy.exc.InvalidRequestError, sqlalchemy.orm.exc.UnmappedInstanceError):
                                    pass
                                continue
                            self.session.add_all(references)
                        else:
                            if len(forms) >= 1:
                                warnings.warn(
                                    f"Found more than one match for {form_cell:}",
                                    MultipleCandidatesWarning)
                            form = forms[0]
                            for attr, value in form_cell.items():
                                reference_value = getattr(form, attr, None)
                                if reference_value != value:
                                    warnings.warn(
                                        f"Reference form property {attr:} was '{reference_value:}', not the '{value:}' specified here.")
                        self.associate(form, row_object)
                self.session.commit()


class ExcelCognateParser(ExcelParser):

    def __init__(self, output_dataset: pycldf.Dataset, excel_file: str, top: int=2, left: int=2,
                 check_for_match: t.List[str] = ["cldf_id"],
                 check_for_row_match: t.List[str] = ["cldf_id"],
                 on_language_not_found: MissingHandler = ExcelParser.warn,
                 on_row_not_found: MissingHandler = ExcelParser.create,
                 on_form_not_found: MissingHandler = ExcelParser.warn,
                 **kwargs) -> None:
        super().__init__(output_dataset, excel_file, top=top, left=left, check_for_match=check_for_match,
                         check_for_row_match=check_for_row_match,
                         on_language_not_found=on_language_not_found, on_row_not_found=on_row_not_found,
                         on_form_not_found=on_form_not_found,
                         override_dataset=True,
                         **kwargs)
        self.cell_parser = CellParserHyperlink()
        self.RowObject = self.CogSet

    def properties_from_row(
            self, row: t.List[openpyxl.cell.Cell]
    ) -> t.Dict[str, t.Any]:
        data = [(cell.value or '').strip() for cell in row[:self.left - 1]]
        comment = get_cell_comment(row[0])
        if not data[0]:
            return {}
        return {
            "cldf_id": data[0],
            "cldf_comment": comment
        }

    def associate(self, form: Form, row: t.Union[Concept, CogSet]) -> None:
        id = new_id(
            f"{form.cldf_id:}_{row.cldf_id:}",
            self.Judgement, self.session)
        self.session.add(self.Judgement(cldf_id=id, form=form, cognateset=row))


class MawetiGuaraniExcelParser(ExcelParser):

    def __init__(self, output_dataset: pycldf.Dataset, excel_file: str, top: int=3, left: int=7,
                 check_for_match: t.List[str]=["sources", "cldf_value"],
                 check_for_row_match: t.List[str]=["cldf_name"],
                 **kwargs) -> None:
        super().__init__(output_dataset, excel_file, top=top, left=left,
                         check_for_match=check_for_match, check_for_row_match=check_for_row_match, **kwargs)
        self.cell_parser = MawetiGuaraniLexicalParser()

    def language_from_column(self, column: t.List[openpyxl.cell.Cell]) -> t.Dict[str, t.Any]:
        data = [(cell.value or '').strip() for cell in column[:2]]
        comment = get_cell_comment(column[0])
        return {
            "cldf_name": data[0],
            "Curator": data[1],
            "cldf_comment": comment
        }

    def properties_from_row(self, row: t.List[openpyxl.cell.Cell]) -> t.Dict[str, t.Any]:
        set, english, english_strict, spanish, portuguese, french = [(cell.value or '').strip() for cell in row]
        comment = get_cell_comment(row[0])
        return {
            "Set": set,
            "English": english_strict,
            "Spanish": spanish,
            "Portuguese": portuguese,
            "French": french,
            "cldf_name": english,
            "cldf_comment": comment
        }


class MawetiGuaraniExcelCognateParser(
        ExcelCognateParser, MawetiGuaraniExcelParser):

    def __init__(self, output_dataset: pycldf.Dataset, excel_file: str, top: int=3, left: int=7,
                 check_for_match: t.List[str]=["cldf_form", "sources", "cldf_value"],
                 check_for_row_match: t.List[str]=["cldf_id"],
                 **kwargs) -> None:
        super().__init__(output_dataset, excel_file, top=top, left=left,
                         check_for_match=check_for_match, check_for_row_match=check_for_row_match,
                         **kwargs)
        self.on_language_not_found = ExcelParser.warn
        self.on_row_not_found = ExcelParser.create
        self.on_form_not_found = ExcelParser.warn
        self.cell_parser = MawetiGuaraniCognateParser()

    def set_up_sheets(self, fname: str) -> None:
        wb = openpyxl.load_workbook(filename=fname)
        self.sheets = [wb[sheet] for sheet in wb.sheetnames]

    def properties_from_row(self, row):
        values = [(cell.value or '').strip() for cell in row[:2]]
        cldf_id = values[1]
        if cldf_id.isupper():
            cldf_id = cldf_id.lower()
        return {
            "cldf_id": cldf_id,
            "properties": values[0],
            "cldf_comment": get_cell_comment(row[1])
        }


def load_mg_style_dataset(
        metadata: Path, lexicon: str, cogsets: str, db: str) -> None:
    if db == "":
        open_file, db = mkstemp(".sqlite", "lexicaldatabase", text=False)
        # The CLDF database functionality expects the file to not exist, so
        # delete it again, but keep the filename.
        os.close(open_file)
        Path(db).unlink()

    # The Intermediate Storage, in a in-memory DB (unless specified otherwise)
    excel_parser_lexical = MawetiGuaraniExcelParser(
        pycldf.Dataset.from_metadata(metadata), fname=db, excel_file=lexicon)
    excel_parser_lexical.parse_cells()
    excel_parser_lexical.cldfdatabase.to_cldf(metadata.parent, mdname=metadata.name)
    excel_parser_cognateset = MawetiGuaraniExcelCognateParser(
        pycldf.Dataset.from_metadata(metadata), fname=db, excel_file=cogsets)
    excel_parser_cognateset.parse_cells()
    excel_parser_cognateset.cldfdatabase.to_cldf(metadata.parent, mdname=metadata.name)


if __name__ == "__main__":
    import argparse
    import pycldf
    parser = argparse.ArgumentParser(description="Load a Maweti-Guarani-style dataset into CLDF")
    parser.add_argument(
        "lexicon", nargs="?",
        default="TG_comparative_lexical_online_MASTER.xlsx",
        help="Path to an Excel file containing the dataset")
    parser.add_argument(
        "cogsets", nargs="?",
        default="TG_cognates_online_MASTER.xlsx",
        help="Path to an Excel file containing cogsets and cognatejudgements")
    parser.add_argument(
        "--db", nargs="?",
        default="",
        help="Where to store the temp from reading the word list")
    parser.add_argument(
        "--metadata", nargs="?", type=Path,
        default="Wordlist-metadata.json",
        help="Path to the metadata.json")
    parser.add_argument(
        "--debug-level", type=int, default=0,
        help="Debug level: Higher numbers are less forgiving")
    args = parser.parse_args()

    if args.db.startswith("sqlite:///"):
        args.db = args.db[len("sqlite:///"):]
    if args.db == ":memory:":
        args.db = ""
    # We have too many difficult database connections in different APIs, we
    # refuse in-memory DBs and use a temporary file instead.

    load_mg_style_dataset(args.metadata, args.lexicon, args.cogsets, args.db)

