# -*- coding: utf-8 -*-
import re

from lexedata.importer.exceptions import *


# functions for bracket checking
one_bracket = lambda opening, closing, str, nr: str[0] == opening and str[-1] == closing and \
                                                (str.count(opening) == str.count(closing) == nr)
comment_bracket = lambda str: str.count("(") == str.count(")")


class CellParser():
    """
    Iterator class over all form elements contained in a form cell
    """

    # pattern for splitting form cell into various form elements, re.sub will be used
    _form_separator = re.compile(r"""^(.+[}\]>)/])        # Anything until the first separator
    \s*              # Any amount of spaces
    [,;]             # Some separator
    \s*              # Any amount of spaces
    ([<{/[].+)       # Followed by the rest of the string""", re.VERBOSE)

    # exemplary pattern to catch phonemic transcription: /.+/ or /.+[%~].+/ or /.+/ [%~]/.+/ [%~]/.+/ ....
    # is repeated for phonetic and orthographic
    phonemic_pattern = re.compile(r"""(?:^| # start of the line or
    (.*?(?<=[^&]))) #capture anything before phonemic, phonemic must not follow a &, i.e. & escapes
    (/.+?/  #first phonemic element, not greedy
    (?:\s*[~%]\s*/.+?/)*  #non capturing pattern for any repetition of [%~]/..../
    )  #capture whole group
    (.*)$ #capture the rest""", re.VERBOSE)
    phonetic_pattern = re.compile(r"(?:^|(.*?(?<=[^&])))(\[.+?](?:\s*[~%]\s*\[.+?])*)(.*)$")
    ortho_pattern = re.compile(r"(?:^|(.*?(?<=[^&])))(<.+?>(?:\s*[~%]\s*<.+?>)*)(.*)$")

    source_pattern = re.compile(r"(?:^|(.*?(?<=[^&])))({.+?})(.*)$")  # just one source per form, must not be empty
    _comment_pattern = re.compile(r"^(.*?)(\(.+\))(.*)$")  # all in brackets, not greedy

    _form_pattern = [(phonemic_pattern, "phonemic"),
                        (phonetic_pattern, "phonetic"),
                        (ortho_pattern, "orthographic"),
                        (source_pattern, "source")]

    _comment_checker = re.compile(r"[^&][</[{].*[>/\]}]")  # for checking with re.search
    _illegal_chars = re.compile(r"[;=]")  # for checking with re.search

    _cleaner = re.compile(r"^(.+)#.+?#(.*)$")  # will clean using re.sub

    def __init__(self, cell):
        values = cell.value
        self.coordinate = cell.coordinate
        if not values:  # capture None values
            raise CellParsingError(values, self.coordinates)
        self.set_elements(values)

    def set_elements(self, values):

        #remove #
        while self._cleaner.match(values):
            values = self._cleaner.sub(r"\1\2", values)
        elements = CellParser.separate(values)

        if len(elements) == 0:  # check that not empty
            raise CellParsingError(values, self.coordinate)

        # clean elements list
        elements = [e.rstrip(" ").lstrip(" ") for e in elements]  # no tailing white spaces
        elements[-1] = elements[-1].rstrip("\n").rstrip(",").rstrip(";") # remove possible line break and ending commas

        self._elements = iter(elements)

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
        while cl._form_separator.match(values):
            values = cl._form_separator.sub(r"\1&&\2", values)
        return values.split("&&")

    @classmethod
    def parsecell(cls, ele, coordinates, cellsize=5):
        """
        :param ele: is a form string; form string referring to a possibly (semicolon or)comma separated string of a form cell
        :return: list of cellsize containing parsed data of form string
        """
        if ele == "...":
            mymatch = ["No value"] * cellsize

        else:
            mymatch = cls.parse_form(ele, coordinates)

        mymatch = [e or '' for e in mymatch]
        phonemic, phonetic, ortho, comment, source = mymatch

        variants = []
        if phonemic:
            phonemic = cls.variants_separator(variants, phonemic, coordinates)
        if phonetic:
            phonetic = cls.variants_separator(variants, phonetic, coordinates)
        if ortho:
            ortho = cls.variants_separator(variants, ortho, coordinates)
        variants = ",".join(variants)

        if phonemic == phonetic == ortho == "":
            raise FormCellError((phonemic + phonetic + ortho), "Empty Cell", coordinates)
        # those tests have currently become obsolete
        #if phonemic != "" and phonemic != "No value":
            #if not one_bracket("/", "/", phonemic, 2):
                #raise FormCellError(phonemic, "phonemic", coordinates)
            # phonemic = phonemic.strip("/")

        #if phonetic != "" and phonetic != "No value":
            #if not one_bracket("[", "]", phonetic, 1):
                #raise FormCellError(phonetic, "phonetic", coordinates)
            # phonetic = phonetic.strip("[").strip("]")

        #if ortho != "" and ortho != "No value":
            #if not one_bracket("<", ">", ortho, 1):
                #raise FormCellError(ortho, "orthographic", coordinates)
            # ortho = ortho.strip("<").strip(">")

        if comment != "" and comment != "No value":
            if not comment_bracket(comment):
                raise FormCellError(comment, "comment", coordinates)

        return [phonemic, phonetic, ortho, comment, source, variants]

    @classmethod
    def parse_form(cls, formele, coordinates):
        """checks if values of cells not in expected order, extract each value"""
        ele = (formele + ".")[:-1] # force python to hard copy string
        d = {"phonemic": None, "phonetic": None, "orthographic": None, "comment": None, "source": None}
        for pat, lable in cls._form_pattern:

            mymatch = pat.match(ele)
            if mymatch:
                # delete match in cell
                d[lable] = mymatch.group(2)
                ele = pat.sub(r"\1\3", ele)

        # get all that is left of the string in () and add it to the comment
        mycomment = ""
        while cls._comment_pattern.match(ele):
            comment_candidate = cls._comment_pattern.match(ele).group(2)
            if not re.search(r"[^&][</\[{]", comment_candidate):
                mycomment += comment_candidate
                ele = cls._comment_pattern.sub(r"\1\3", ele)
            else:
                raise FormCellError(comment_candidate, "comment", coordinates)

        # check that ele was parsed entirely
        # add wrong ordered cell to error message of CellParser
        # raise error
        ele = ele.strip(" ")
        if not ele == "":
            # if just text left and no comment given, put text in comment
            # more than one token
            if len(ele) >= 1 and (not re.search(r"[<>/\[\]}{]", ele)):

                if not mycomment:
                    mycomment =  ele
                else:
                    mycomment += ele

            else:
                errmessage = "after parsing {}  -  {} was left unparsed".format(formele, ele)
                raise FormCellError(errmessage, "IncompleteParsingError; probably illegal content", coordinates)

        # enclose comment if not properly enclosed
        if mycomment != "" and (not mycomment.startswith("(") or not mycomment.endswith(")")):
            mycomment = "(" + mycomment + ")"
        d["comment"] = mycomment
        form_cell = [d["phonemic"], d["phonetic"], d["orthographic"], d["comment"], d["source"]]
        return form_cell


    @staticmethod
    def variants_scanner(string, symbol):
        """copies string, inserting closing brackets after symbol if necessary"""
        is_open = False
        closers = {"<": ">", "[": "]", "/": "/"}
        collector = ""
        starter = ""

        for char in string:

            if char in closers and not is_open:
                collector += char
                is_open = True
                starter = char

            elif char == symbol:
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
    def variants_separator(cls, variants_list, string, coordinate):
        if cls._illegal_chars.search(string):
            raise SeparatorCellError(string, coordinate)
        # force python to copy string
        text = (string + "&")[:-1]
        text = text.replace(" ", "")
        if "~" in string:
            values = cls.variants_scanner(text, "~")
            values = values.split("~")
            first = values.pop(0)

            # add rest to variants prefixed with ~
            values = [("~" + e) for e in values]
            variants_list += values
            return first

        # inconsistent variants
        elif "%" in string:
            values = cls.variants_scanner(text, "%")
            values = values.split("%")
            first = values.pop(0)

            # add rest to variants prefixed with ~
            values = [("%" + e) for e in values]
            variants_list += values
            return first
        else:
            return string

    def __iter__(self):
        return self

    def __next__(self):
        try:
            ele = next(self._elements)
            ele = CellParser.parsecell(ele, self.coordinate)
            # check core values not empty
            phonemic, phonetic, ortho = ele[0], ele[1], ele[2]
            if phonemic == phonetic == ortho == "":
                raise CellParsingError("empty values ''", self.coordinate)
            return ele

        except CellParsingError as err:
            print("CellParsingError: " + err.message)
            # input()
            return self.__next__()

        except FormCellError as err:
            print(err)
            # input()
            return self.__next__()

        except IgnoreCellError as err:
            print(err)
            # input()
            return self.__next__()

        except SeparatorCellError as err:
            print(err)
            # input()
            return self.__next__()

    def __iter__(self):
        return self


class CogCellParser(CellParser):

    def __init__(self, cell):
        values = cell.value
        self.coordinate = cell.coordinate

        if values.isupper():
            print(IgnoreCellError(values, self.coordinate))

        self.set_elements(values)



class Tester():

    def __init__(self, string, coordinate="asf"):
        self.value = string
        self.coordinate = coordinate

    def __hash__(self):
        return self


if __name__ == "__main__":

    c1 = Tester("<tatatĩ>(humo){Guasch1962:717}, <timbo>(vapor, vaho, humareda, humo){Guasch1962:729};<tĩ> (humo, vapor de agua)$LDM:deleted 'nariz, pico, hocico, punta, and ápica' meanings; source incorrectly merges 'point' and 'smoke' meanings ${Guasch1962:729}")
    c2 = Tester("/pãlĩ/ (de froment = wheat) (NCP: loan from french farine), /pɨlatɨ/ (de mais cru), /kuʔi/ (de mais grillé)")
    c3 = Tester("/pãlĩ/ (de froment = wheat(NCP: loan from french farine), &<dummy>), /pɨlatɨ/ (de mais cru), /kuʔi/ (de mais grillé)")
    c4 = Tester("/popɨãpat/ 'back of elbow' {4}")
    c5 = Tester("<ayu> (&<yayu> 'sein Hals') {2}")
    for ele in [c1, c2, c3, c4, c5]:
        print(ele.value)
        print("is represented as: ")
        for f in CogCellParser(ele):
            print(f)



