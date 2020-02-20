# -*- coding: utf-8 -*-
import openpyxl as op
import csv
import re
from collections import defaultdict
import unidecode as uni
import argparse
import pycldf
import attr
import sqlalchemy as sa
from sqlalchemy.ext.declarative import as_declarative, declared_attr
from sqlalchemy.orm import sessionmaker

from .exceptions import *
from .cellparser import CellParser

# Initialize the SQL Alchemy
import os
try:
    os.remove("cldf.sqlite")
except FileNotFoundError:
    pass

engine = sa.create_engine('sqlite:///cldf.sqlite', echo=True) # Create an SQLite database in this directory

session = sessionmaker(bind=engine)()

#replacing none values with ''
replace_none = lambda x: "" if x == None else x

#lambda function for getting comment of excel cell if comment given
replace_none_comment = lambda x: x.content if x  else ""
comment_getter = lambda x: replace_none_comment(x.comment)

# replacing none values with ''
replace_none = lambda x: "" if x == None else x

# lambda function for getting comment of excel cell if comment given
replace_none_comment = lambda x: x.content if x else ""
comment_getter = lambda x: replace_none_comment(x.comment)

# functions for bracket checking
one_bracket = lambda opening, closing, str, nr: str[0] == opening and str[-1] == closing and \
                                                (str.count(opening) == str.count(closing) == nr)
comment_bracket = lambda str: str.count("(") == str.count(")")

# header for files
header_forms = ["form_id", "language_id",
                "phonemic", "phonetic", "orthography", "variants", "source", "form_comment",
                "concept_comment"]

header_concepts = ["concept_id",
                   "set", "english", "english_strict", "spanish", "portuguese", "french", "concept_comment"]

header_languages = ["language_id",
                    "language_name", "curator", "language_comment"]


# header_form_concept = ["form_id", "concept_id"]

invalid_id_elements = re.compile(r"\W+")


@as_declarative()
class DatabaseObjectWithUniqueStringID:
    @declared_attr
    def __tablename__(cls):
        return cls.__name__.lower()

    id = sa.Column(sa.String, primary_key=True)

    @staticmethod
    def string_to_id(string):
        """

        >>> string_to_id("trivial")
        "trivial"
        >>> string_to_id("just 4 non-alphanumerical characters.")
        >>> string_to_id("Это русский.")
        >>> string_to_id("该语言有一个音节。")
        >>> string_to_id("この言語には音節があります。")

        """
        # We nee to run this through valid_id_elements twice, because some word
        # characters are unidecoded to contain non-word characters.
        return valid_id_elements.sub("_", uni.unidecode(valid_id_elements.sub("_", string)).lower())

    @classmethod
    def register_new_id(cl, id):
        assert id == cl.string_to_id(id)
        try:
            registry = cl.__registry
        except AttributeError:
            registry = set(o.id for o in session.query(cl.id))
        i = 1
        while "{:s}{:d}".format(id, i) in registry:
            i += 1
        unique = "{:s}{:d}".format(id, i)
        registry.add(unique)
        return unique

print(DatabaseObjectWithUniqueStringID.string_to_id("教育部重編國語辭典修訂本xtxexsxtxâxäxγxωxまxax字x-xまx‿x۳xqxaxaxlxixaxtxex xwx–xaxшxnx੩xnx"))

class Language(DatabaseObjectWithUniqueStringID):
    """Metadata for a language"""
    name = sa.Column(sa.String)
    curator = sa.Column(sa.String)
    comments = sa.Column(sa.String)
    coordinates = sa.Column(sa.String)

    @classmethod
    def from_column(k, column):
        name, curator = [cell.value for cell in column]
        id = k.register_new_id(k.string_to_id(name))
        return k(id=id, name=name, curator=curator, comments="", coordinates="??")

    # pycldf.Dataset.write assumes a `get` method to access attributes, so we
    # can make `LanguageCell` outputtable to CLDF by providing such a method,
    # mapping attributes to CLDF column names
    def get(self, property, default=None):
        if property == "language_id" or property == "ID":
            return self.id
        elif property == "language_name" or property == "name":
            return self.name
        elif property == "curator":
            return self.curator
        elif property == "language_comment" or property == "comments":
            return self.comments
        return default

    def warn(self):
        if "???" in self.name:
            raise LanguageElementError(coordinates, self.name)


class Form(DatabaseObjectWithUniqueStringID):
    language_id = sa.Column(sa.String)

    phonemic = sa.Column(sa.String)
    phonetic = sa.Column(sa.String)
    orthographic = sa.Column(sa.String)
    variants = sa.Column(sa.String)
    comment = sa.Column(sa.String)
    source = sa.Column(sa.String)

    form_comment = sa.Column(sa.String)

    @classmethod
    def create_form(klasse, form_id, lan_id, con_com, form_com, values, coordinates):
        phonemic, phonetic, ortho, comment, source = values

        variants = []
        phonemic = klasse.variants_separator(variants, phonemic)
        phonetic = klasse.variants_separator(variants, phonetic)
        ortho = klasse.variants_separator(variants, ortho)

        if phonemic != "" and phonemic != "No value":
            if not one_bracket("/", "/", phonemic, 2):
                raise FormCellError(coordinates, phonemic, "phonemic")
            # phonemic = phonemic.strip("/")

        if phonetic != "" and phonetic != "No value":
            if not one_bracket("[", "]", phonetic, 1):
                raise FormCellError(coordinates, phonetic, "phonetic")
            # phonetic = phonetic.strip("[").strip("]")

        if ortho != "" and ortho != "No value":
            if not one_bracket("<", ">", ortho, 1):
                raise FormCellError(coordinates, ortho, "orthographic")
            # ortho = ortho.strip("<").strip(">")

        if comment != "" and comment != "No value":
            if not comment_bracket(comment):
                raise FormCellError(coordinates, comment, "comment")

        # replace source if not given
        source = "{1}" if source == "" else source

        return klasse(id=form_id, language_id=lan_id, phonemic=phonemic, phonetic=phonetic, orthographic=ortho,
                      variants=variants, comment=comment, source=source,
                      form_comment=form_com)

    __variants_corrector = re.compile(r"^([</\[])(.+[^>/\]])$")
    __variants_splitter = re.compile(r"^(.+?)\s?~\s?([</\[].+)$")

    @staticmethod
    def variants_scanner(string):
        """copies string, inserting closing brackets if necessary"""
        is_open = False
        closers = {"<": ">", "[": "]", "/": "/"}
        collector = ""
        starter = ""

        for char in string:

            if char in closers and not is_open:
                collector += char
                is_open = True
                starter = char

            elif char == "~":
                if is_open:
                    collector += (closers[starter] + char + starter)
                else:
                    collector += char

            elif char in closers.values():
                collector += char
                is_open = False
                starter = ""

            elif is_open:
                collector += char

        return collector

    @classmethod
    def variants_separator(klasse, variants_list, string):
        if "~" in string:
            # force python to copy string
            text = (string + "&")[:-1]
            text = text.replace(" ", "")
            text = text.replace(",", "")
            text = text.replace(";", "")
            values = klasse.variants_scanner(text)

            values = values.split("~")
            first = values.pop(0)
            variants_list += values
            return first
        else:
            return string

    __form_counter = defaultdict(int)

    @classmethod
    def id_creator(klasse, lan_id, con_id):
        return klasse.string_to_id("{:s}_{:s}_".format(lan_id, con_id))

    def get(self, property, default=None):
        if property == "form_id" or property == "ID":
            return self.id
        elif property == "language_id" or property == "Language_ID":
            return self.language_id
        elif property == "phonemic":
            return self.phonemic
        elif property == "phonetic":
            return self.phonetic
        elif property == "orthographic":
            return self.orthographic
        elif property == "source":
            return self.source
        elif property == "comment":
            return self.comment
        elif property == "form_comment":
            return self.form_comment
        elif property == "variants":
            return self.variants
        return default


class Concept(DatabaseObjectWithUniqueStringID):
    """
    a concept element consists of 8 fields:
        (concept_id,set,english,english_strict,spanish,portuguese,french,concept_comment)
    sharing concept_id and concept_comment with a form element
    concept_comment refers to te comment of the cell containing the english meaning
    """
    set = sa.Column(sa.String)
    english = sa.Column(sa.String)
    english_strict = sa.Column(sa.String)
    spanish = sa.Column(sa.String)
    portuguese = sa.Column(sa.String)
    french = sa.Column(sa.String)
    concept_comment = sa.Column(sa.String)
    coordinates = sa.Column(sa.String)

    @classmethod
    def row_to_concept(klasse, conceptrow):
        # values of cell
        set, english, english_strict, spanish, portugese, french = [replace_none(cell.value) for cell in conceptrow]
        # comment of cell
        concept_comment = comment_getter(conceptrow[1])
        # create id
        concept_id = klasse.register_new_id(klasse.string_to_id(english))
        return klasse(id=concept_id, set=set, english=english, english_strict=english_strict, spanish=spanish,
                      portuguese=portugese, french=french, concept_comment=concept_comment, coordinates="??")

    # protected static class variable for creating unique ids, regex-pattern
    _conceptdict = defaultdict(int)
    __id_pattern = re.compile(r"^(.+?)(?:[,\(\@](?:.+)?|)$")

    def get(self, property, default=None):
        if property == "concept_id":
            return self.id
        elif property == "set":
            return self.set
        elif property == "english":
            return self.english
        elif property == "english_strict":
            return self.english_strict
        elif property == "spanish":
            return self.spanish
        elif property == "portuguese":
            return self.portuguese
        elif property == "french":
            return self.french
        return default

DatabaseObjectWithUniqueStringID.metadata.create_all(engine, checkfirst=True)


def main():
    parser = argparse.ArgumentParser(description="Load a Maweti-Guarani-style dataset into CLDF")
    parser.add_argument(
        "path", nargs="?",
        default="./Copy of TG_comparative_lexical_online_MASTER.xlsx",
        help="Path to an Excel file containing the dataset")
    parser.add_argument(
        "output", nargs="?",
        default="./",
        help="Directory to create the output CLDF wordlist in")
    parser.add_argument(
        "--debug-level", type=int, default=0,
        help="Debug level: Higher numbers are less forgiving")
    args = parser.parse_args()

    wb = op.load_workbook(filename=args.path)
    sheets = wb.sheetnames

    iter_forms = wb[sheets[0]].iter_rows(min_row=3, min_col=7, max_col=44)  # iterates over rows with forms

    iter_concept = wb[sheets[0]].iter_rows(min_row=3, max_col=6)  # iterates over rows with concepts

    with open("forms_ms.csv", "w", encoding="utf8", newline="") as formsout, \
            open("concepts_ms.csv", "w", encoding="utf8", newline="") as conceptsout, \
            open("languages_ms.csv", "w", encoding="utf8", newline="") as lanout:

        formscsv = csv.DictWriter(formsout, header_forms, extrasaction="ignore", quotechar='"',
                                  quoting=csv.QUOTE_MINIMAL)
        formscsv.writeheader()

        concsv = csv.DictWriter(conceptsout, header_concepts, extrasaction="ignore", quotechar='"',
                                quoting=csv.QUOTE_MINIMAL)
        concsv.writeheader()

        lancsv = csv.DictWriter(lanout, header_languages, extrasaction="ignore", quotechar='"',
                                quoting=csv.QUOTE_MINIMAL)
        lancsv.writeheader()

        # Collect languages
        languages = {}
        # TODO: The following line contains a magic number, can we just iterate until we are done?
        for lan_col in wb[sheets[0]].iter_cols(min_row=1, max_row=2, min_col=7, max_col=44):
            # iterate over language columns
            lan_cell = Language.from_column(lan_col)
            session.add(lan_cell)

            # Switch to warnings module or something similar for this
            if args.debug_level >= 2:
                lan_cell.warn()
            elif args.debug_level == 1:
                try:
                    lan_cell.warn()
                except LanguageElementError as E:
                    print(E)
                    continue

            languages[lan_cell.name] = lan_cell

            lancsv.writerow(lan_cell)
        session.commit()

        formcells = []
        for row_forms, row_con in zip(iter_forms, iter_concept):

            concept_cell = Concept.row_to_concept(row_con)
            con_comment = concept_cell.concept_comment

            concsv.writerow(concept_cell)

            for i, f_cell in enumerate(row_forms):
                if f_cell.value:

                    # you can access the cell's column letter and just add 1
                    this_lan_name = wb[sheets[0]][(f_cell.column_letter + "1")].value
                    this_lan_id = languages[this_lan_name].id
                    f_comment = comment_getter(f_cell)

                    try:

                        for f_ele in CellParser(f_cell):
                            f_ele = [replace_none(e) for e in f_ele]

                            form_id = Form.id_creator(this_lan_id, concept_cell.id)

                            c_form = Form.create_form(
                                form_id = form_id,
                                lan_id = this_lan_id,
                                con_com = con_comment,
                                form_com = f_comment,
                                values = f_ele,
                                coordinates = f_cell.coordinate)
                            formcells.append(c_form)
                            formscsv.writerow(c_form)

                    except CellParsingError as err:
                        print("CellParsingError - somethings quite wrong")
                        print(err.message)
                        input()



                    except FormCellError as err:
                        print(("original cell content: - " + f_cell.value))
                        print(("failed form element: - " + str(f_ele)))
                        print(err)
                        input()

        #################################################
        # create cldf
        dataset = pycldf.Wordlist.in_dir(args.output)

        dataset.add_component("LanguageTable")
        dataset.write(LanguageTable=list(languages.values()), FormTable=formcells)


if __name__ == "__main__":
    __package__ = "lexedata.importer"
    main()
