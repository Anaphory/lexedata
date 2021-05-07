"""Starting with a forms.csv, add metadata for all columns we know about.
"""

from pathlib import Path

import pycldf
from csvw.dsv import iterrows
from csvw.metadata import Column, Datatype

from lexedata import cli

DEFAULT_NAME_COLUMNS = {
    column.name: column
    for column in (term.to_column() for term in pycldf.TERMS.values())
}

LEXEDATA_COLUMNS = {
    "Status": Column(
        datatype=Datatype(base="string"),
        default="",
        lang="eng",
        null=[""],
        name="Value",
        aboutUrl="...",
    ),
    "Orthographic": Column(
        datatype=Datatype(base="string"),
        default="",
        null=[""],
        name="Orthographic",
        aboutUrl="...",
    ),
    "Phonemic": Column(
        datatype=Datatype(base="string"),
        default="",
        null=[""],
        name="Phonemic",
        aboutUrl="...",
    ),
    "Phonetic": Column(
        datatype=Datatype(base="string"),
        default="",
        null=[""],
        name="Phonetic",
        aboutUrl="...",
    ),
    "Variants": Column(
        datatype=Datatype(base="string", format=r"\s*(~|)\s*[[/(].*[]/)]\s*"),
        separator=",",
        default="",
        null=[""],
        name="Variants",
    ),
    "Tags": Column(
        datatype=Datatype(base="string"),
        separator=",",
        default="",
        null=[""],
        name="Tags",
    ),
    "Loan": Column(
        datatype=Datatype(base="string"),
        default="",
        null=[""],
        name="Loan",
        aboutUrl="...",
    ),
}

LINGPY_COLUMNS = {
    "IPA": pycldf.TERMS["form"].to_column(),
    "DOCULECT": pycldf.TERMS["languageReference"].to_column(),
}

OTHER_KNOWN_COLUMNS = {
    "Form_according_to_Source": Column(
        datatype=Datatype(base="string"),
        default="",
        null=[""],
        name="Form_according_to_Source",
        required=True,
    ),
    "Page": Column(
        datatype=Datatype(base="string", format=r"\d+(-\d+)?"),
        separator=",",
        default="",
        null=["", "?"],
        name="Page",
    ),
}


if __name__ == "__main__":
    parser = cli.parser(__doc__)
    args = parser.parse_args()
    logger = cli.setup_logging(args)

    # TODO, maybe: allow specification of the file by command line option. In that
    # case, check for name and extension and make sure to write the metadata to
    # the same folder.
    fname = Path("forms.csv")

    ds = pycldf.Wordlist.from_data(fname)
    # `from_data` checks that the reqired columns of the FormTable are present,
    # but it does not consolidate the columns further.

    colnames = next(iterrows(fname))

    understood_colnames = {
        c.name for c in ds[ds.primary_table].tableSchema.columns if c.name in colnames
    }

    # Consider the columns that were not understood.
    columns_without_metadata = set(colnames) - understood_colnames
    for column_name in columns_without_metadata:
        column: Column
        # Maybe they are known CLDF properties?
        if column_name in pycldf.terms.TERMS:
            column = pycldf.TERMS[column_name].to_column()
            column.name = column_name
        # Maybe they are CLDF default column names?
        elif column_name in DEFAULT_NAME_COLUMNS:
            column = DEFAULT_NAME_COLUMNS[column_name]
        # Maybe they are columns that Lexedata knows to handle?
        elif column_name in LEXEDATA_COLUMNS:
            column = LEXEDATA_COLUMNS[column_name]
        # Maybe they are columns inherited from LingPy?
        elif column_name.upper() in LINGPY_COLUMNS:
            column = LINGPY_COLUMNS[column_name.upper()]
            column.name = column_name
        # Maybe they are some name we have seen before?
        elif column_name in OTHER_KNOWN_COLUMNS:
            column = OTHER_KNOWN_COLUMNS[column_name]
        else:
            # Maybe they look like they have a specific type?
            ...
            # Otherwise, they are probably just text to be kept.
            column = Column(
                datatype=Datatype(base="string"),
                default="",
                null=[""],
                name=column_name,
            )

        ds[ds.primary_table].tableSchema.columns.append(column)

    ds[ds.primary_table].tableSchema.columns.sort(
        key=lambda k: colnames.index(k.name) if k.name in colnames else 1e10
    )

    ds.write_metadata(args.metadata)

    ds.validate(log=logger)
