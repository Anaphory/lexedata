import pycldf
import argparse
import typing as t
from pathlib import Path

from lexedata.enrich.add_status_column import add_status_column_to_table

# TODO: use lexedata.change.clean_ids.update_ids
# TODO: share more functionality with rename_concept


def substitute_many(
    row, columns, old_values_to_new_values, status_update: t.Optional[str]
):
    for column in columns:
        if type(row[column]) == list:
            row[column] = [
                old_values_to_new_values.get(val, val) for val in row[column]
            ]
            if status_update:
                row["Status_Column"] = status_update
        elif type(row[column]) == str:
            row[column] = old_values_to_new_values.get(row[column], row[column])
            if status_update:
                row["Status_Column"] = status_update
    return row


def rename(ds, old_values_to_new_values, status_update: t.Optional[str]):
    languages = ds["LanguageTable"]

    for table in ds.tables:
        if table == languages:
            continue
        _, component = table.common_props["dc:conformsTo"].split("#")
        try:
            c_language = ds[component, "languageReference"]
            columns = {c_language.name}
        except KeyError:
            columns = set()
        for reference in table.tableSchema.foreignKeys:
            if reference.reference.resource.string == languages.url.string:
                (column,) = reference.columnReference
                columns.add(column)
        if columns:
            print(f"Changing columns {columns:} in {component:}…")
            ds.write(
                **{
                    component: [
                        substitute_many(
                            r,
                            columns,
                            old_values_to_new_values,
                            status_update=status_update,
                        )
                        for r in table
                    ]
                }
            )


def replace_column(
    dataset: pycldf.Dataset,
    original: str,
    replacement: str,
    column_replace: bool,
    smush: bool,
    status_update: t.Optional[str],
) -> None:
    # add Status_column if not existing and status update given
    if status_update:
        add_status_column_to_table(dataset=dataset, table_name="LanguageTable")

    if column_replace:
        assert (
            original == "id" or original == dataset["LanguageTable", "id"].name
        ), f"Replacing an entire column is only meaningful when you change the #id column ({dataset['LanguageTable', 'id'].name}) of the LanguageTable."

        c_id = dataset["LanguageTable", original].name
        c_new = dataset["LanguageTable", replacement].name
        mapping = {
            language[c_id]: language[c_new] for language in dataset["LanguageTable"]
        }
        assert smush or len(mapping) == len(
            set(mapping.values())
        ), "Would collapse some languages that were distinct before! Add '--smush' if that is intended."
        # dataset["LanguageTable"].tableSchema.columns["c_id"]
        rename(dataset, mapping, status_update=status_update)
    else:
        languages = dataset["LanguageTable"]

        c_id = dataset["LanguageTable", "id"].name

        print(f"Changing {c_id:} of LanguageTable")
        dataset.write(
            LanguageTable=[
                substitute_many(r, [c_id], {original: replacement}, status_update=None)
                for r in languages
            ]
        )
        rename(dataset, {original: replacement}, status_update=status_update)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Change the ID of a language in the wordlist"
    )
    parser.add_argument(
        "original", type=str, help="Name of the original column to be replaced"
    )
    parser.add_argument("replacement", type=str, help="Name of the replacement column")
    parser.add_argument(
        "--metadata",
        type=Path,
        default="Wordlist-metadata.json",
        help="Path to the JSON metadata file describing the dataset (default: ./Wordlist-metadata.json)",
    )
    parser.add_argument("--column-replace", action="store_true", default=False)
    parser.add_argument("--smush", action="store_true", default=False)
    parser.add_argument(
        "--status-update",
        type=str,
        default="default",
        help="Text written to Status_Column. Set to 'None' for no status update. "
        "(default: Replaced column {original} by column {replacement}",
    )
    args = parser.parse_args()
    if args.status_update == "None":
        args.status_update = None
    if args.status_update == "default":
        args.status_update = (
            f"Replaced column {args.original} by column {args.replacement}"
        )

    replace_column(
        dataset=pycldf.Dataset.from_metadata(args.metadata),
        original=args.original,
        replacement=args.replacement,
        column_replace=args.column_replace,
        smush=args.smush,
        status_update=args.status_update,
    )
