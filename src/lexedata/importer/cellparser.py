# -*- coding: utf-8 -*-
import re
import logging
import typing as t
import openpyxl

from lexedata.error_handling import *
from lexedata.util import string_to_id
from lexedata.types import Form


logger = logging.getLogger(__name__)



def check_brackets(string, bracket_pairs):
    """Check whether all brackets match.

    This function can check the matching of simple bracket pairs, like this:

    >>> b = {"(": ")", "[": "]", "{": "}"}
    >>> check_brackets("([])", b)
    True
    >>> check_brackets("([]])", b)
    False
    >>> check_brackets("([[])", b)
    False
    >>> check_brackets("This (but [not] this)", b)
    True

    But it can also deal with multi-character matches

    >>> b = {"(": ")", "begin": "end"}
    >>> check_brackets("begin (__ (!) xxx) end", b)
    True
    >>> check_brackets("begin (__ (!) end) xxx", b)
    False

    This includes multi-character matches where some pair is a subset of
    another pair. Here the order of the pairs in the dictionary is important –
    longer pairs must be defined first.

    >>> b = {":::": ":::", ":": ":"}
    >>> check_brackets("::: :::", b)
    True
    >>> check_brackets("::::::", b)
    True
    >>> check_brackets("::::", b)
    False
    >>> check_brackets(":: ::", b)
    True

    In combination, these features allow for natural escape sequences:

    >>> b = {"!(": "", "!)": "", "(": ")", "[": "]"}
    >>> check_brackets("(text)", b)
    True
    >>> check_brackets("(text", b)
    False
    >>> check_brackets("text)", b)
    False
    >>> check_brackets("(te[xt)]", b)
    False
    >>> check_brackets("!(text", b)
    True
    >>> check_brackets("text!)", b)
    True
    >>> check_brackets("!(te[xt!)]", b)
    True
    """
    waiting_for = []
    i = 0
    while i < len(string):
        if waiting_for and string[i:].startswith(waiting_for[0]):
            i += len(waiting_for.pop(0))
        else:
            for q, p in bracket_pairs.items():
                if string[i:].startswith(q):
                    waiting_for.insert(0, p)
                    i += len(q)
                    break
                elif p and string[i:].startswith(p):
                    return False
            else:
                i += 1
    return not any(waiting_for)


def components_in_brackets(form_string, bracket_pairs):
    """Find all elements delimited by complete pairs of matching brackets.

    >>> b = {"!/": "", "(": ")", "[": "]", "{": "}", "/": "/"}
    >>> components_in_brackets("/aha/ (exclam. !/ int., also /ah/)", b)
    ['', '/aha/', ' ', '(exclam. !/ int., also /ah/)', '']

    Recovery from mismatched delimiters early in the string is difficult. The
    following example is still waiting for the first '/' to be closed by the
    end of the string.

    >>> components_in_brackets("/aha (exclam. !/ int., also /ah/)", b)
    ['', '/aha (exclam. !/ int., also /ah/)']

    """
    elements = []

    i = 0
    remainder = form_string
    waiting_for = []
    while i < len(remainder):
        if waiting_for and remainder[i:].startswith(waiting_for[0]):
            i += len(waiting_for.pop(0))
            if not any(waiting_for):
                elements.append(remainder[:i])
                remainder = remainder[i:]
                i = 0
        else:
            for q, p in bracket_pairs.items():
                if remainder[i:].startswith(q):
                    if not any(waiting_for):
                        elements.append(remainder[:i])
                        remainder = remainder[i:]
                        i = 0
                    waiting_for.insert(0, p)
                    i += len(q)
                    break
                elif p and remainder[i:].startswith(p):
                    logger.warning(f"In form {form_string}: Encountered mismatched closing delimiter {p}")
            else:
                i += 1
    return elements + [remainder]


class NaiveCellParser():
    def separate(self, values: str) -> t.Iterable[str]:
        """Separate different form descriptions in one string.

        Separate forms separated by comma.
        """
        return values.split(",")

    def source_from_source_string(
            self,
            source_string: str,
            language_id: t.Optional[str]) -> t.Tuple[str, t.Optional[str]]:
        """Parse a string referencing a language-specific source

        >>> b = NaiveCellParser()
        >>> b.source_from_source_string("{1}", "abui")
        ('abui_s1', None)
        >>> b.source_from_source_string("", "abui")
        ('abui_s', None)
        >>> b.source_from_source_string("{Gul2020: p. 4}", "abui")
        ('abui_sgul2020', 'p. 4')

        """
        context: t.Optional[str]
        if ":" in source_string:
            source_part, context = source_string.split(":", maxsplit=1)
            if not context.endswith("}"):
                logger.warning(f"In source {source_string}: Closing bracket '}}' is missing, split into source and page/context may be wrong")
            source_string = source_part + "}"
            context = context[:-1].strip()
        else:
            context = None

        if source_string.startswith("{") and source_string.endswith("}"):
            source_string = source_string[1:-1]
        if language_id is None:
            source_id = string_to_id(source_string)
        else:
            source_id = string_to_id(f"{language_id:}_s{source_string:}")

        return source_id, context

    def parse_form(self, form_string: str, language_id: str,
            cell_identifier: str = ''
    ) -> t.Optional[Form]:
        return Form({
            "cldf_value": form_string,
            "cldf_form": form_string.strip(),
            "cldf_languageReference": language_id
        })

    def parse(self, cell: openpyxl.cell.Cell, language_id: str,
            cell_identifier: str = ''
    ) -> t.Iterable[Form]:
        """Return form properties for every form in the cell

        """
        if not cell.value:
            return []

        for element in self.separate(cell.value):
            try:
                breakpoint()
                form = self.parse_form(element, language_id, cell_identifier)
            except CellParsingError as err:
                continue
            if form:
                yield form


class CellParser(NaiveCellParser):
    def __init__(self,
                 bracket_pairs: t.Dict[str, str] = {
                    "(": ")",
                    "[": "]",
                    "{": "}",
                    "<": ">",
                    "/": "/"},
                 element_semantics: t.Dict[str, str] = {
                    "(": ("cldf_comment", False),
                    "[": ("phonetic", True),
                    "{": ("cldf_source", False),
                    "<": ("orthographic", True),
                    "/": ("phonemic", True)},
                 separation_pattern: str = r"([;,])",
                 variant_separator: t.Optional[list] = None,
                 add_default_source: str = "{1}"):
        self.bracket_pairs = bracket_pairs
        self.element_semantics = element_semantics
        self.separation_pattern = separation_pattern
        self.variant_separator = variant_separator
        self.add_default_source = add_default_source

    def separate(self, values: str) -> t.Iterable[str]:
        """Separate different form descriptions in one string.

        Separate forms separated by comma or semicolon, unless the comma or
        semicolon occurs within a set of matching component delimiters (eg.
        brackets)

        If the brackets don't match, the whole remainder string is passed on,
        so that the form parser can try to recover as much as possible or throw
        an exception.

        >>> b = CellParser()
        >>> list(b.separate("hic, haec, hoc"))
        ['hic', 'haec', 'hoc']
        >>> list(b.separate("hic (this, also: here); hoc"))
        ['hic (this, also: here)', 'hoc']
        >>> list(b.separate("hic (this, also: here"))
        ['hic (this, also: here']
        >>> list(b.separate("illic,"))
        ['illic']

        """
        raw_split = re.split(self.separation_pattern, values)
        while len(raw_split) > 1:
            if check_brackets(raw_split[0], self.bracket_pairs):
                form = raw_split.pop(0).strip()
                if form:
                    yield form
                raw_split.pop(0)
            else:
                raw_split[:2] = [''.join(raw_split[:2])]
        form = raw_split.pop(0).strip()
        if form:
            yield form
        assert not raw_split

    def parse_form(
            self, form_string: str, language_id: str,
            cell_identifier: str = '',
    ) -> t.Optional[Form]:
        """Create a dictionary of columns from a form description.

        Extract each value (transcriptions, comments, sources etc.) from a
        string describing a single form.

        >>> c = CellParser()
        >>> c.parse_form(" \t", "abui") == None
        True

        """
        # if string is only whitespaces, there is no form.
        if not form_string.strip():
            return None
        # cell_identifier format: sheet.cell_coordinate
        cell_identifier = '{}: '.format(cell_identifier) if cell_identifier else ''

        properties: t.Dict[str, t.Any] = {
            "cldf_languageReference": language_id,
            "cldf_value": form_string}

        # Semantics: 'None' for no variant expected, any string for the
        # decorator that introduces variant forms. Currently we expect '~' and
        # '%', see below.
        expect_variant: t.Optional[str] = None
        # Iterate over the delimiter-separated elements of the form.
        for element in components_in_brackets(form_string, self.bracket_pairs):
            element = element.strip()

            if not element:
                continue

            # If the element has mismatched brackets (tends to happen only for
            # the last element, because a mismatched opening bracket means we
            # are still waiting for the closing one), warn.
            if not check_brackets(element, self.bracket_pairs):
                logger.warning(f"{cell_identifier}In form {form_string}: Element {element} had mismatching delimiters")

            # Check what kind of element we have.
            for start, field in self.element_semantics.items():
                field = field[0]
                if element.startswith(start):
                    break
            else:
                # The only thing we expect outside delimiters is the variant
                # separators, '~' and '%'.
                if self.variant_separator and element in self.variant_separator:
                    expect_variant = element
                else:
                    logger.warning(f"{cell_identifier}In form {form_string}: Element {element} could not be parsed, ignored")
                continue

            # If we encounter a field for the first time, we add it to the
            # dictionary. If repeatedly, to the variants, with a decorator that
            # shows how expected the variant was.
            # This drops sources and comments in variants, if more than one source or comment is provided
            # clean this up in self.postprocessing

            if field in properties:
                if not expect_variant and field != "cldf_comment" and field != "cldf_source":
                    logger.warning(f"{cell_identifier}In form {form_string}: Element {element} was an unexpected variant for {field}")
                properties.setdefault("variants", []).append(
                    (expect_variant or '') +
                    element)
            else:
                if expect_variant:
                    logger.warning(f"{cell_identifier}In form {form_string}: Element {element} was supposed to be a variant, but there is no earlier {field}")
                properties[field] = element

            expect_variant = None

        self.postprocess_form(properties, language_id)
        return Form(properties)

    def postprocess_form(
            self,
            properties: t.Dict[str, t.Any],
            language_id: str) -> None:
        """Modify the form in-place

        Fix some properties of the form. This is the place to add default
        sources, cut of delimiters, split unmarked variants, etc.

        """
        # TODO: Once everything seems to work fine, remove delimiters from the
        # raw elements, and adjust the tests to not expect those delimiters
        # -> I'm not sure about including this in the general cellparser, it might affect postprocessing we'd like
        # -> to perform in the MawatiCellParser

        # TODO: Currently "..." lands in the forms, with empty other entries
        # (and non-empty source). This is not too bad for now, how should it
        # be?
        source = properties.pop("cldf_source", None)
        if self.add_default_source and source is None:
            source = self.add_default_source
        if source:
            source, context = self.source_from_source_string(source, language_id)
            properties["cldf_source"] = {(source, context)}



class CellParserHyperlink(CellParser):
    def parse(
            self, cell: openpyxl.cell.Cell, language_id: str, cell_identifier: str = ''
    ) -> t.Iterable[Form]:
        try:
            url = cell.hyperlink.target
            yield Form({"ID": url.split("/")[-1]})
        except AttributeError:
            pass


class MawetiCellParser(CellParser):
        # TODO: Write a subclass for Maweti-Guarani that also uses what we know
        # about that dataset:
        # • TODO Pick out the two- or three-letter editor
        #   procedural comments.
        # • TODO: Split forms that contain '%' or '~', drop the variant in
        #   variants.
    def __init__(self,
                 bracket_pairs: t.Dict[str, str],
                 element_semantics: t.Dict[str, str],
                 separation_pattern: str,
                 variant_separator: list,                 add_default_source: str):
        super(MawetiCellParser, self).__init__(bracket_pairs=bracket_pairs,
                                               element_semantics=element_semantics,
                                               separation_pattern=separation_pattern,
                                               variant_separator=variant_separator,
                                               add_default_source=add_default_source)

    def postprocess_form(
            self,
            properties: t.Dict[str, t.Any],
            language_id: str) -> None:
        """
        >>> m = MawetiCellParser()
        >>> form = {
        ...  "orthographic": "<lexedata % lexidata>",
        ...  "phonemic": "/lεksedata ~ lεksidata/"
        ...  "variants": ["(from lexicon + edit + data)", "(another comment)"]
        ...  "cldf_comment": "(GAK: We should pick one of those names, I'm 80% sure it should be the first)"
        ... }
        >>> m.postprocess_form(form, "abui1241")
        >>> form == {"orthographic": "lexedata",
        ...  "phonemic": "lεksedata",
        ...  "variants": ["~ <lexidata>", "~ /lεksidata/"],
        ...  "cldf_comment": "from lexicon + edit + data\\tanother comment",
        ...  "cldf_source": {("abui1241_s1", None)}
        ...  "procedural_comment": "GAK: We should pick one of those names, I'm 80% sure it should be the first"}
        True
        """
        super().postprocess_form(properties, language_id)
        # catch procedural comments (e.g. NPC: ...) in cldf_comments and add to corresponding field
        # but a procedural comment could land in variants, thus this case needs to be checked as well
        try:
            comment = properties["cldf_comment"]
            beginning = comment[1:5]
            if beginning[:3].isupper() and beginning[-1] == ":":
                properties["procedural_comment"] = comment
                del properties["cldf_comment"]
        except KeyError:
            pass

        # TODO: Ask Gereon: What kind of separator between comments and sources?
        # if variants already exists, it may contain a actual variant, additional comments or sources
        start_of_comment = ""
        start_of_source = ""
        for k, v in self.element_semantics.items():
            if v[0] == "cldf_comment":
                start_of_comment = k
            if v[0] == "cldf_source":
                start_of_source = k
        try:
            actual_variants = []
            for variant in properties["variants"]:
                start = variant[0]
                # check for actual variants
                if start in self.variant_separator:
                    actual_variants.append(variant)

                # check for misplaced comments
                elif start == start_of_comment:
                    # check if it s a procedural comment
                    if re.search(r"^[A-Z]{2,}:", variant[1:]):
                        try:
                            properties["procedural_comment"] += variant
                        except KeyError:
                            properties["procedural_comment"] = variant
                    else:
                        try:
                            properties["cldf_comment"] += variant
                        except KeyError:
                            properties["cldf_comment"] = variant

                # check for misplaced sources
                elif start == start_of_source:
                    properties.setdefault(
                        "cldf_source", set()).add(
                            self.source_from_source_string(variant))

            properties["variants"] = actual_variants
        except KeyError:
            pass

        # Split transcriptions of form that contain '%' or '~', drop the variant in
        transcriptions = [semantics[0] for semantics in self.element_semantics.values() if semantics[1]]
        # if variants not in properties, add default list
        variants = properties.setdefault("variants", [])
        for key in transcriptions:
            try:
                value = properties[key]
            except KeyError:
                continue
            # if any separator is in this value, split value. add first as key and rest to variants.
            if self.variant_separator:
                for separator in self.variant_separator:
                    if separator in value:
                        # split string with variants
                        # add first transcription as transcription, rest to variants
                        # TODO: ensure correct opening and closing of brackets? Left out for now, as brackets will
                        # removed in the end
                        value = value.split(separator)
                        properties[key] = value.pop(0)
                        for v in value:
                            variants.append((separator + v))

        # post processing of base class
        super().postprocess_form(properties, language_id)


class MawetiCognateCellParser(MawetiCellParser):
    def parse_form(self, values, language, cell_identifier: str = ''):
        if values.isupper():
            return None
        else:
            return super().parse_form(values, language, cell_identifier)

