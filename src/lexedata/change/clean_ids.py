"""Clean up all ID columns in the datasat.

Take every ID column and convert it to either an integer-valued or a restricted-string-valued (only containing a-z, 0-9, or _) column, maintaining uniqueness of IDs, and keeping IDs as they are where they fit the format.

Optionally, create ‘transparent’ IDs, that is alphanumerical IDs which are derived from the characteristic columns of the corresponding table. For example, the ID of a FormTable would be derived from language and concept; for a CognatesetTable from the central concept if there is one.

"""

import typing as t

import csvw.metadata
import pycldf

from lexedata import cli
from lexedata.util import ID_FORMAT, string_to_id, cache_table

ID_COMPONENTS: t.Mapping[str, t.Sequence[str]] = {
    "FormTable": ["languageReference", "parameterReference"]
}


def clean_mapping(rows: t.Mapping[str, t.Mapping[str, str]]) -> t.Mapping[str, str]:
    """Create unique normalized IDs.

    >>> clean_mapping({"A": {}, "B": {}})
    {'A': 'a', 'B': 'b'}

    >>> clean_mapping({"A": {}, "a": {}})
    {'A': 'a', 'a': 'a_x2'}
    """
    avoid = {id.lower() for id in rows}

    mapping: t.Dict[str, str] = {}
    for id, row in rows.items():
        i = 1
        if row:
            base = string_to_id("_".join(row.values()))
        else:
            base = string_to_id(id)

        if base in avoid and base not in mapping.values():
            # I kept a spot for you!
            mapping[id] = base
            continue

        # Make sure ID is unique
        tentative_mapping = base
        while tentative_mapping in avoid or tentative_mapping in mapping.values():
            i += 1
            tentative_mapping = "{:}_x{:}".format(base, i)
        mapping[id] = tentative_mapping

    return mapping


def update_ids(
    ds: pycldf.Dataset, table: csvw.metadata.Table, mapping: t.Mapping[str, str]
):
    """Update all IDs of the table in the database, also in foreign keys."""
    c_id = table.get_column("http://cldf.clld.org/v1.0/terms.rdf#id")
    rows = []
    for row in cli.tq(ds[table], total=ds[table].common_props.get("dc:extent")):
        row[c_id.name] = mapping.get(row[c_id.name], row[c_id.name])
        rows.append(row)
    logger.info(f"Writing {table.url.string} back to file…")
    table.write(rows)

    c_id.datatype.format = ID_FORMAT.pattern

    foreign_keys_to_here = {
        other_table.url.string: {
            foreign_key.columnReference[
                foreign_key.reference.columnReference.index(c_id.name)
            ]
            for foreign_key in other_table.tableSchema.foreignKeys
            if foreign_key.reference.resource == table.url
            if c_id.name in foreign_key.reference.columnReference
        }
        for other_table in ds.tables
    }
    for other_table, columns in foreign_keys_to_here.items():
        if not columns:
            continue
        logger.info(f"Applying changed foreign key to {other_table}…")
        rows = []
        for row in cli.tq(
            ds[other_table], total=ds[other_table].common_props.get("dc:extent")
        ):
            for column in columns:
                row[column] = mapping.get(row[column], row[column])
            rows.append(row)
        logger.info(f"Writing {other_table} back to file…")
        ds[other_table].write(rows)

        for column in columns:
            ds[other_table, column].datatype = c_id.datatype


if __name__ == "__main__":
    parser = cli.parser(__doc__)
    parser.add_argument(
        "--transparent",
        action="store_true",
        default=False,
        help="Generate transparent IDs.",
    )
    args = parser.parse_args()
    logger = cli.setup_logging(args)

    ds = pycldf.Wordlist.from_metadata(args.metadata)

    for table in ds.tables:
        logger.info(f"Handling table {table.url.string}…")
        ttype = ds.get_tabletype(table)
        c_id = table.get_column("http://cldf.clld.org/v1.0/terms.rdf#id")
        if c_id.datatype.base == "string":
            ...
        elif c_id.datatype.base == "integer":
            continue
        else:
            logger.warning(
                f"Table {table.uri} had an id column ({c_id.name}) that is neither integer nor string. I did not touch it."
            )
            continue

        if args.transparent and ttype in ID_COMPONENTS:
            cols = {prop: ds[ttype, prop].name for prop in ID_COMPONENTS[ttype]}
            mapping = clean_mapping(cache_table(ds, ttype, cols))
        else:
            ids = {row[c_id.name] for row in ds[table]}
            mapping = clean_mapping(cache_table(ds, table.url.string, {}))

        update_ids(ds, table, mapping)

    ds.write_metadata()
