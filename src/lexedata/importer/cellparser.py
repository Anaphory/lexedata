# -*- coding: utf-8 -*-
import re

from .exceptions import *
from .objects import Form

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


class CellParser():
    """
    Iterator class over all form elements contained in a form cell
    """
    _wrongorder = [] #just for checking correct parsing

    #pattern for splitting form cell into various form elements
    form_separator = re.compile(r"""
    (?<=[}\)>/\]])    # The end of an element of transcription, not consumed
    \s*               # Any amount of spaces
    [,;]              # Some separator
    \s*               # Any amount of spaces
    (?=[</\[])        # Followed by the beginnig of any transcription, but don't consume that bit""",
        re.VERBOSE)
    # pattern for parsing content of cell
    __cell_value_pattern = re.compile(r"^(/.+?/)?\s?(\[.+?\])?\s?(<.+?>)?\s?(\(.+\))?\s?(\{.+\})?$")
    __special_pattern = [re.compile(e) for e in [r"^.*(/.+/).*$",
                                                r"^.*(\[.+?\]).*$",
                                                r"^.*(<.+?>).*$",
                                                r"^.*(\(.+\)).*$",
                                                r"^.*(\{.+?\}).*$"]
                       ]

    def __init__(self, cell, lan_id, concept):
        values = cell.value

        elements = CellParser.separate(values)

        if len(elements) == 0: # check that not empty
            raise CellParsingError(values)

        # clean elements list
        elements = [e.rstrip(" ").lstrip(" ") for e in elements]  # no tailing white spaces
        elements[-1] = elements[-1].rstrip("\n").rstrip(",").rstrip(";") # remove possible line break and ending commas

        self._elements = iter(elements)
        self.lan_id = lan_id
        self.concept = concept

    @classmethod
    def separate(cl, values):
        """Splits the content of a form cell into single form descriptions

        >>> CellParser.separate("<jaoca> (apartar-se, separar-se){2}")
        ['<jaoca> (apartar-se, separar-se){2}']
        >>> CellParser.separate("<eruguasu> (adj); <eniãcũpũ> (good-tasting (sweet honey, hard candy, chocolate candy, water){2}; <beyiruubu tuti> (tasty (re: meat with salt, honey, all good things)){2}; <eniacõ> (tasty (re: eggnog with flavoring)){2}; <eracũpũ> (tasty, good re: taste of honey, smell of flowers)){2}; <eribia tuti> (very tasty){2}; <ericute~ecute> (tasty, good (boiled foods)){2}; <eriya sui tuti> (very tasty, re: fermented fruit){2}; <erochĩpu> (good, tasty (re: tembe, pig meat)){2}; <ichẽẽ> (tasty (taste of roasted meat)){2}")[1]
        '<eniãcũpũ> (good-tasting (sweet honey, hard candy, chocolate candy, water){2}'

        Returns
        =======
        list of form strings
        """
        return re.split(cl.form_separator, values)

    @staticmethod
    def parsecell(ele, cellsize=5):
        """
        :param ele: is a form string; form string referring to a possibly (semicolon or)comma separated string of a form cell
        :return: list of cellsize containing parsed data of form string
        """
        mymatch = CellParser.__cell_value_pattern.match(ele)

        # check for match
        if mymatch:
            mymatch = list(mymatch.groups())  # tuple of all matches, None if empty
            return mymatch

        #check for exceptions
        else:
            if ele == "...":
                ele = ["No value"] * cellsize
                return ele

            elif len(ele) > 3: #cell not None nor ..., could be in wrong order
                ele= CellParser.wrong_order(ele, cellsize=cellsize)
                return ele

            else: #cell cannot be parsed
                raise CellParsingError(ele)

    @staticmethod
    def wrong_order(formele, cellsize=5):
        """checks if values of cells not in expected order, extract each value"""
        ele = (formele + ".")[:-1] # force python to hard copy string
        empty_cell = [None] * cellsize
        for i, pat in enumerate(CellParser.__special_pattern):
            mymatch = pat.match(ele)
            if mymatch:
                # delete match in cell
                empty_cell[i] = mymatch.group(1)
                ele = pat.sub("", ele)

        # check that ele was parsed entirely
        # add wrong ordered cell to error messag of CellParser
        # raise error
        ele = ele.strip(" ")
        if not ele == "":

            errmessage = formele +"\n" + str(empty_cell)
            CellParser._wrongorder.append(errmessage)
            raise CellParsingError(errmessage, comment="in wrong order: ")

        return empty_cell

    def __iter__(self):
        return self

    def __next__(self):
        ele = next(self._elements)
        return create_form(CellParser.parsecell(ele), self.lan_id, self.concept)

def create_form(f_ele, lan_id, concept):
    f_ele = [e or '' for e in f_ele]

    phonemic, phonetic, ortho, comment, source = f_ele

    form_id = Form.register_new_id(
        Form.id_creator(lan_id, concept.ID))

    variants = []
    phonemic = Form.variants_separator(variants, phonemic)
    phonetic = Form.variants_separator(variants, phonetic)
    ortho = Form.variants_separator(variants, ortho)

    if phonemic != "" and phonemic != "No value":
        if not one_bracket("/", "/", phonemic, 2):
            raise FormCellError(phonemic, "phonemic")
        # phonemic = phonemic.strip("/")

    if phonetic != "" and phonetic != "No value":
        if not one_bracket("[", "]", phonetic, 1):
            raise FormCellError(phonetic, "phonetic")
        # phonetic = phonetic.strip("[").strip("]")

    if ortho != "" and ortho != "No value":
        if not one_bracket("<", ">", ortho, 1):
            raise FormCellError(ortho, "orthographic")
        # ortho = ortho.strip("<").strip(">")

    if comment != "" and comment != "No value":
        if not comment_bracket(comment):
            raise FormCellError(comment, "comment")

    # replace source if not given
    source_id = lan_id + ("{1}" if source == "" else source).strip()

    return Form(ID=form_id, Language_ID=lan_id, phonemic=phonemic,
                phonetic=phonetic, orthographic=ortho,
                variants=";".join(variants)), comment.strip(), source_id
