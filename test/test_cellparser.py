# -*- coding: utf-8 -*-
import pytest
import unicodedata
import argparse
from pathlib import Path
import json
from collections import OrderedDict

from lexedata.importer import cellparser as c



def n(s: str):
    return unicodedata.normalize("NFKC", s)


def test_cellparser_error():
    parser = c.NaiveCellParser()
    assert parser.parse_form("form ", "language") == {
        "cldf_form": "form",
        "cldf_languageReference": "language",
        "cldf_value": "form ",
    }


@pytest.fixture
def parser():
    return c.CellParser()


def test_cellparser_empty(parser):
    # white spaces in excel cell
    assert parser.parse_form(" ", "language") is None


def test_cellparser_1(parser):
    form = parser.parse_form("<tɨ̈nɨmpɨ̈'ä>[tɨ̃nɨ̃mpɨ̃ã; hɨnampɨʔa]", "l1")
    assert form["cldf_source"] == {("l1_s1", None)}
    assert n(form["cldf_value"]) == n("<tɨ̈nɨmpɨ̈'ä>[tɨ̃nɨ̃mpɨ̃ã; hɨnampɨʔa]")
    assert n(form["orthographic"]) == n("tɨ̈nɨmpɨ̈'ä")
    assert n(form["phonetic"]) == n("tɨ̃nɨ̃mpɨ̃ã; hɨnampɨʔa")


def test_cellparser_2(parser):
    form = parser.parse_form("/ta/ [ta.'ʔa] ['ta] (cabello púbico){4}", "language")
    assert form == {
        "cldf_comment": "cabello púbico",
        "cldf_languageReference": "language",
        "cldf_source": {("language_s4", None)},
        "cldf_value": "/ta/ [ta.'ʔa] ['ta] (cabello púbico){4}",
        "phonemic": "ta",
        "phonetic": "ta.'ʔa",
        "variants": ["['ta]"],
        "cldf_form": "ta.'ʔa"
    }


def test_cellparser_3(parser):
    form = parser.parse_form("[dʒi'tɨka] {2} ~ [ʒi'tɨka] {2}", "language")
    assert form == {
        "cldf_languageReference": "language",
        "cldf_source": {("language_s2", None)},
        "cldf_value": "[dʒi'tɨka] {2} ~ [ʒi'tɨka] {2}",
        "phonetic": "dʒi'tɨka",
        "variants": ["~[ʒi'tɨka]", "{2}"],
        "cldf_form": "dʒi'tɨka"
    }


def test_cellparser_4(parser):
    form = parser.parse_form(" /a/ [a.'ʔa] (cabello){4} /aʔa/", "language")
    assert form == {
        "cldf_comment": "cabello",
        "cldf_languageReference": "language",
        "cldf_source": {("language_s4", None)},
        "cldf_value": " /a/ [a.'ʔa] (cabello){4} /aʔa/",
        "phonemic": "a",
        "phonetic": "a.'ʔa",
        "variants": ["/aʔa/"],
        "cldf_form": "a.'ʔa"
    }


def test_cellparser_5(parser):
    form = parser.parse_form("[iɾũndɨ] (H.F.) (parir)", "language")
    assert form["cldf_comment"] == "H.F."
    assert form["cldf_source"] == {("language_s1", None)}
    assert n(form["cldf_value"]) == n("[iɾũndɨ] (H.F.) (parir)")
    assert n(form["phonetic"]) == n("iɾũndɨ")
    assert form["variants"] == ["(parir)"]


def test_cellparser_6(parser):
    form = parser.parse_form("(GIVE BIRTH) [mbohaˈpɨ]", "language")
    assert form == {
        "cldf_comment": "GIVE BIRTH",
        "cldf_languageReference": "language",
        "cldf_source": {("language_s1", None)},
        "cldf_value": "(GIVE BIRTH) [mbohaˈpɨ]",
        "phonetic": "mbohaˈpɨ",
        "cldf_form": "mbohaˈpɨ"
    }


def test_cellparser_7(parser):
    form = parser.parse_form("[dʒi'tɨka] ~ [ʒi'tɨka] {2} {2}", "language")
    assert form == {
        "cldf_languageReference": "language",
        "cldf_source": {("language_s2", None)},
        "cldf_value": "[dʒi'tɨka] ~ [ʒi'tɨka] {2} {2}",
        "phonetic": "dʒi'tɨka",
        "variants": ["~[ʒi'tɨka]", "{2}"],
        "cldf_form": "dʒi'tɨka"
    }


def test_cellparser_8(parser):
    # comment error due to not matching opening and closing brackets
    form = parser.parse_form(
        "<eniãcũpũ> (good-tasting (sweet honey, hard candy, chocolate candy, water))){2}",  # noqa: E501
        "language",
    )
    assert (
        form["cldf_comment"]
        == "good-tasting (sweet honey, hard candy, chocolate candy, water)"
    )
    assert form["cldf_languageReference"] == "language"
    assert n(form["cldf_value"]) == n(
        "<eniãcũpũ> (good-tasting (sweet honey, hard candy, chocolate candy, water))){2}",  # noqa: E501
    )
    assert n(form["orthographic"]) == n("eniãcũpũ")
    assert not form.get("phonemic")


def test_cellparser_separate_1(parser):
    assert list(
        parser.separate("[iɾũndɨ] (H.F.) (parir), (GIVE BIRTH) [mbohaˈpɨ]")
    ) == ["[iɾũndɨ] (H.F.) (parir)", "(GIVE BIRTH) [mbohaˈpɨ]"]


def test_cellparser_separate_2(parser):
    assert len(list(parser.separate("<tɨ̈nɨmpɨ̈'ä>[tɨ̃nɨ̃mpɨ̃ã; hɨnampɨʔa]"))) == 1


@pytest.fixture
def mawetiparser():
    metadata = Path(__file__).parent / "data/cldf/smallmawetiguarani/cldf-metadata.json"
    dialect = argparse.Namespace(
        **json.load(metadata.open("r", encoding="utf8"))["special:fromexcel"]
    )
    element_semantics = OrderedDict()
    bracket_pairs = OrderedDict()
    for value in dialect.cell_parser["cell_parser_semantics"]:
        name, opening, closing, my_bool = value
        bracket_pairs[opening] = closing
        element_semantics[opening] = (name, my_bool)
    initialized_cell_parser = getattr(c, dialect.cell_parser["name"])(
        bracket_pairs=bracket_pairs,
        element_semantics=element_semantics,
        separation_pattern=fr"([{''.join(dialect.cell_parser['form_separator'])}])",
        variant_separator=dialect.cell_parser["variant_separator"],
        add_default_source=dialect.cell_parser["add_default_source"],
    )
    return initialized_cell_parser


def test_mawetiparser_no_dublicate_sources(mawetiparser):
    form = mawetiparser.parse_form("[dʒi'tɨka] {2} ~ [ʒi'tɨka] {2}", "language")
    assert form == {
        "cldf_languageReference": "language",
        "cldf_source": {("language_s2", None)},
        "cldf_value": "[dʒi'tɨka] {2} ~ [ʒi'tɨka] {2}",
        "phonetic": "dʒi'tɨka",
        "variants": ["~[ʒi'tɨka]"],
        "cldf_form": "dʒi'tɨka"
    }


def test_mawetiparser_multiple_comments(mawetiparser):
    form = mawetiparser.parse_form(
        "/etakɾã/ [e.ta.'kɾã] ~[test_variant with various comments] (uno; solo) "
        "(test comment) (test comment 2){4}",
        "language",
    )
    assert form == {
        "cldf_languageReference": "language",
        "cldf_source": {("language_s4", None)},
        "cldf_value": "/etakɾã/ [e.ta.'kɾã] ~[test_variant with various comments] (uno; solo) "
        "(test comment) (test comment 2){4}",
        "phonetic": "e.ta.'kɾã",
        "phonemic": "etakɾã",
        "cldf_comment": "uno; solo\ttest comment\ttest comment 2",
        "variants": ["~[test_variant with various comments]"],
        "cldf_form": "e.ta.'kɾã"
    }
