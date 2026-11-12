"""Compare two dataset revisions by their real Parquet files, audit what the MCP reads, and check the dataset.

Commands (any subset, in one run):
  schema    footers of every table in latest/ and history/* at both revisions: added, removed and retyped columns,
            tables and snapshots; snapshots whose schema differs from latest
  values    distinct values of low-cardinality string columns in latest/ at both revisions (vocabulary changes)
  coverage  target columns that the hf_parquet adapter never reads: candidates to expose
  checks    consistency checks of the target dataset; every failure is a DATASET ISSUE for a change request

Column paths use the notation of the dataset's docs/dataset/schema.json: struct fields joined by '.', '[]' for lists.

Usage: uv run python .claude/skills/update-dataset/scripts/dataset_diff.py schema values coverage checks \\
           --base REV --target REV
"""
import argparse
import json
import re
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path

import pyarrow as pa
import pyarrow.compute as pc
import pyarrow.parquet as pq
from _common import MCP_ROOT, REPO_ID, dataset_repo_file, parse_tag, section
from huggingface_hub import HfApi, HfFileSystem, hf_hub_download
from huggingface_hub.hf_api import RepoFile

Columns = dict[str, str]
LATEST = "latest"


def flatten(data_type: pa.DataType, prefix: str = "") -> Columns:
    if pa.types.is_struct(data_type):
        result: Columns = {}
        for child in data_type:
            result |= flatten(child.type, f"{prefix}.{child.name}" if prefix else child.name)
        return result
    if pa.types.is_list(data_type) or pa.types.is_large_list(data_type):
        return flatten(data_type.value_type, f"{prefix}[]")
    return {prefix: str(data_type)}


def flatten_schema(schema: pa.Schema) -> Columns:
    result: Columns = {}
    for column in schema:
        result |= flatten(column.type, column.name)
    return result


@dataclass
class Revision:
    """The parquet schemas and metadata.json of every snapshot of one revision."""
    name: str
    schemas: dict[str, dict[str, Columns]] = field(default_factory=dict)  # snapshot -> table -> columns
    metadata: dict[str, dict[str, object]] = field(default_factory=dict)  # snapshot -> metadata.json

    @property
    def history(self) -> list[str]:
        return sorted(s for s in self.schemas if s != LATEST)

    def latest(self, table: str) -> Columns:
        return self.schemas.get(LATEST, {}).get(table, {})

    @property
    def tables(self) -> set[str]:
        return set(self.schemas.get(LATEST, {}))


def _snapshot_of(path: str) -> str:
    parts = path.split("/")
    return LATEST if parts[0] == LATEST else parts[1]


def load_revision(api: HfApi, name: str, workers: int) -> Revision:
    files = [f for folder in (LATEST, "history")
             for f in api.list_repo_tree(REPO_ID, path_in_repo=folder, repo_type="dataset", revision=name,
                                         recursive=True)
             if isinstance(f, RepoFile)]
    parquet = [f for f in files if "/parquet/" in f.path and f.path.endswith(".parquet")]
    metadata = [f for f in files if f.path.endswith("/metadata.json")]
    fs = HfFileSystem()

    def read_schema(file: RepoFile) -> Columns:
        with fs.open(f"datasets/{REPO_ID}/{file.path}", "rb", revision=name) as handle:
            return flatten_schema(pq.read_schema(handle))

    def read_metadata(file: RepoFile) -> dict[str, object]:
        path = hf_hub_download(REPO_ID, file.path, repo_type="dataset", revision=name)
        result: dict[str, object] = json.loads(Path(path).read_text())
        return result

    revision = Revision(name)
    with ThreadPoolExecutor(workers) as pool:
        for file, columns in zip(parquet, pool.map(read_schema, parquet)):
            revision.schemas.setdefault(_snapshot_of(file.path), {})[Path(file.path).stem] = columns
        for file, meta in zip(metadata, pool.map(read_metadata, metadata)):
            revision.metadata[_snapshot_of(file.path)] = meta
    return revision


@dataclass
class ColumnDiff:
    added: Columns
    removed: Columns
    retyped: dict[str, tuple[str, str]]

    @property
    def empty(self) -> bool:
        return not (self.added or self.removed or self.retyped)


def diff_columns(old: Columns, new: Columns) -> ColumnDiff:
    return ColumnDiff(
        added={c: t for c, t in new.items() if c not in old},
        removed={c: t for c, t in old.items() if c not in new},
        retyped={c: (old[c], new[c]) for c in old.keys() & new.keys() if old[c] != new[c]},
    )


def _parent(column: str) -> str:
    return column.rsplit(".", 1)[0] if "." in column else ""


def print_diff(diff: ColumnDiff, indent: str = "  ") -> None:
    for column, data_type in sorted(diff.added.items()):
        print(f"{indent}+ {column}: {data_type}")
    for column, data_type in sorted(diff.removed.items()):
        print(f"{indent}- {column}: {data_type}")
    for column, (old, new) in sorted(diff.retyped.items()):
        print(f"{indent}~ {column}: {old} -> {new}")
    for gone, gone_type in sorted(diff.removed.items()):
        for new, new_type in sorted(diff.added.items()):
            if gone_type == new_type and _parent(gone) == _parent(new) and gone.endswith("[]") == new.endswith("[]"):
                print(f"{indent}? possible rename {gone} -> {new}")


def snapshot_divergence(revision: Revision) -> dict[str, dict[str, ColumnDiff]]:
    """table -> snapshot -> how its columns differ from latest/ of the same revision."""
    result: dict[str, dict[str, ColumnDiff]] = defaultdict(dict)
    for snapshot in revision.history:
        for table in revision.tables | set(revision.schemas[snapshot]):
            diff = diff_columns(revision.latest(table), revision.schemas[snapshot].get(table, {}))
            if not diff.empty:
                result[table][snapshot] = diff
    return result


def null_typed(revision: Revision) -> dict[str, list[str]]:
    """'table.column' -> snapshots where the column has the Arrow null type (no values, so no type)."""
    result: dict[str, list[str]] = defaultdict(list)
    for snapshot, tables in sorted(revision.schemas.items()):
        for table, columns in tables.items():
            for column, data_type in columns.items():
                if data_type == "null":
                    result[f"{table}.{column}"].append(snapshot)
    return result


def cmd_schema(base: Revision, target: Revision) -> None:
    section(f"Snapshots {base.name} -> {target.name}")
    added, removed = set(target.history) - set(base.history), set(base.history) - set(target.history)
    print(f"{len(base.history)} -> {len(target.history)}; added: {', '.join(sorted(added)) or 'none'}; "
          f"removed: {', '.join(sorted(removed)) or 'none'}")

    section("Tables in latest/")
    print(f"added: {', '.join(sorted(target.tables - base.tables)) or 'none'}; "
          f"removed: {', '.join(sorted(base.tables - target.tables)) or 'none'}")

    section("Columns of latest/ (+ added, - removed, ~ retyped)")
    for table in sorted(base.tables | target.tables):
        diff = diff_columns(base.latest(table), target.latest(table))
        print(f"{table}: {'no change' if diff.empty else ''}")
        print_diff(diff)

    section(f"Snapshots of {target.name} whose schema differs from its latest/")
    divergence = snapshot_divergence(target)
    if not divergence:
        print("none: every snapshot has the schema of latest/")
    for table, snapshots in sorted(divergence.items()):
        for snapshot, diff in sorted(snapshots.items()):
            print(f"{table} @ {snapshot}:")
            print_diff(diff, "    ")


def _values(table: pa.Table, column: str) -> pa.Array:
    names = column.split(".")
    first = names[0]
    array: pa.Array = table.column(first.removesuffix("[]")).combine_chunks()
    for _ in range(first.count("[]")):
        array = pc.list_flatten(array)
    for name in names[1:]:
        array = array.field(name.removesuffix("[]"))
        for _ in range(name.count("[]")):
            array = pc.list_flatten(array)
    return array


def _distinct(revision: str, table: str, columns: Columns, max_distinct: int) -> dict[str, set[str] | int]:
    path = hf_hub_download(REPO_ID, f"{LATEST}/parquet/{table}.parquet", repo_type="dataset", revision=revision)
    wanted = [c for c, t in columns.items() if t in ("string", "large_string", "bool")]
    data = pq.read_table(path, columns=sorted({c.split(".")[0].removesuffix("[]") for c in wanted}))
    result: dict[str, set[str] | int] = {}
    for column in wanted:
        unique = pc.unique(_values(data, column).drop_null())
        result[column] = {str(v) for v in unique.to_pylist()} if len(unique) <= max_distinct else len(unique)
    return result


def cmd_values(base: Revision, target: Revision, max_distinct: int) -> None:
    section(f"Distinct values of string columns in latest/ (at most {max_distinct}; + new, - gone)")
    skipped = 0
    for table in sorted(target.tables):
        old = _distinct(base.name, table, base.latest(table), max_distinct) if table in base.tables else {}
        new = _distinct(target.name, table, target.latest(table), max_distinct)
        for column, values in sorted(new.items()):
            before = old.get(column)
            if isinstance(values, int) or isinstance(before, int):
                skipped += 1
            elif before is None:
                print(f"{table}.{column} (new column): {sorted(values)}")
            elif values != before:
                print(f"{table}.{column}: + {sorted(values - before)} - {sorted(before - values)}")
    print(f"({skipped} high-cardinality columns not compared)")


def _referenced(source: str, table: str, column: str) -> bool:
    """Whether the hf_parquet adapter reads the column: by its path, or through an enclosing struct read whole."""
    def found(pattern: str) -> bool:
        return re.search(pattern, source) is not None

    parts = column.replace("[]", "").split(".")
    if table != "data":
        return found(rf"(?<![\w.]){re.escape(parts[0])}(?!\w)")
    if found(rf"(?<![\w.]){re.escape('.'.join(parts))}(?!\w)"):
        return True
    leaf = re.escape(parts[-1])
    for i in range(len(parts) - 1, 0, -1):
        prefix = re.escape(".".join(parts[:i]))
        if (found(rf'"{prefix}"')  # passed through as is, e.g. ("forks", "forks", ...)
                or found(rf"to_json\({prefix}\)(?!, '\$)")  # the whole struct as JSON
                or (found(rf"TRY_CAST\({prefix} AS") and found(rf"(?<![\w.]){leaf} [A-Z]"))  # cast to an explicit type
                or (found(rf"to_json\({prefix}\)") and found(rf"'\$\.{leaf}'"))):  # json_extract of one field
            return True
    return False


def cmd_coverage(target: Revision) -> None:
    adapter = MCP_ROOT / "src" / "anki_addons_mcp" / "adapters" / "hf_parquet"
    source = "\n".join(p.read_text() for p in sorted(adapter.glob("*.py")))
    section("Target columns that the hf_parquet adapter never reads (candidates to expose)")
    total = 0
    for table in sorted(target.tables):
        missing = [f"{c}: {t}" for c, t in target.latest(table).items() if not _referenced(source, table, c)]
        total += len(missing)
        print(f"{table}: {'all read' if not missing else ''}")
        for line in missing:
            print(f"  {line}")
    print(f"{total} column(s) not read. The match is a heuristic: confirm by reading the code.")


def cmd_checks(base: Revision, target: Revision) -> int:
    issues: list[str] = []

    def issue(text: str) -> None:
        issues.append(text)

    tag = parse_tag(target.name)
    versions = {s: str(m.get("dataset_version")) for s, m in target.metadata.items()}
    latest_version = versions.get(LATEST)
    for snapshot in [LATEST, *target.history]:
        if snapshot not in target.metadata:
            issue(f"{snapshot}/metadata.json is missing")
        elif "dataset_version" not in target.metadata[snapshot]:
            issue(f"{snapshot}/metadata.json has no dataset_version")
        elif versions[snapshot] != latest_version:
            issue(f"{snapshot}/metadata.json says dataset_version {versions[snapshot]}, latest/ says {latest_version}")
    if tag and latest_version and tag.dataset_version != latest_version:
        issue(f"tag {target.name} names dataset_version {tag.dataset_version}, latest/metadata.json says "
              f"{latest_version}")

    missing_tables = {s: target.tables - set(t) for s, t in target.schemas.items() if target.tables - set(t)}
    for snapshot, tables in sorted(missing_tables.items()):
        issue(f"snapshot {snapshot} lacks the table(s) {', '.join(sorted(tables))} that latest/ has")

    base_version = base.metadata.get(LATEST, {}).get("dataset_version")
    if base_version is not None and latest_version is not None and base.name != target.name:
        breaking = any(diff_columns(base.latest(t), target.latest(t)).removed
                       or diff_columns(base.latest(t), target.latest(t)).retyped for t in base.tables) \
            or bool(base.tables - target.tables)
        additive = any(diff_columns(base.latest(t), target.latest(t)).added for t in target.tables) \
            or bool(target.tables - base.tables)
        old_major, old_minor = (int(x) for x in str(base_version).split("."))
        new_major, new_minor = (int(x) for x in latest_version.split("."))
        if breaking and new_major <= old_major:
            issue(f"columns or tables were removed, renamed or retyped, but dataset_version went {base_version} -> "
                  f"{latest_version} instead of a MAJOR bump")
        elif additive and (new_major, new_minor) <= (old_major, old_minor):
            issue(f"columns or tables were added, but dataset_version stayed {latest_version} instead of a MINOR bump")
        elif new_major > old_major and not breaking:
            print(f"NOTE: MAJOR bump {base_version} -> {latest_version} without a schema break: a change of meaning? "
                  "Read the changelog.")

    script = str(target.metadata.get(LATEST, {}).get("script_version", ""))
    schema_text = dataset_repo_file(script, "docs/dataset/schema.json") if script else None
    if schema_text is None:
        issue(f"docs/dataset/schema.json not found at the dataset repo tag v{script}")
    else:
        documented = json.loads(schema_text)
        if str(documented.get("dataset_version")) != latest_version:
            issue(f"schema.json at v{script} says dataset_version {documented.get('dataset_version')}, the data says "
                  f"{latest_version}")
        documented_tables: dict[str, Columns] = documented.get("tables", {})
        for table in sorted(set(documented_tables) | target.tables):
            diff = diff_columns(documented_tables.get(table, {}), target.latest(table))
            if not diff.empty:
                lines = [f"+ {c}: {t} (in the data only)" for c, t in sorted(diff.added.items())]
                lines += [f"- {c}: {t} (in schema.json only)" for c, t in sorted(diff.removed.items())]
                lines += [f"~ {c}: schema.json {o}, data {n}" for c, (o, n) in sorted(diff.retyped.items())]
                issue(f"latest/{table}.parquet disagrees with schema.json at v{script}:\n    " + "\n    ".join(lines))

    for table, diverging in sorted(snapshot_divergence(target).items()):
        names = sorted(diverging)
        issue(f"{table}.parquet in {len(names)} snapshot(s) ({names[0]} .. {names[-1]}) has another schema than "
              "latest/, though one revision should share one schema (run `schema` for the columns)")
    for column, snapshots in sorted(null_typed(target).items()):
        issue(f"{column} has the Arrow null type (no type) in {len(snapshots)} snapshot(s): {', '.join(snapshots)}")

    section(f"Dataset checks of {target.name}")
    for number, text in enumerate(issues, 1):
        print(f"DATASET ISSUE {number}: {text}")
    print(f"{len(issues)} dataset issue(s)" if issues else "No dataset issues found")
    return len(issues)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("commands", nargs="+", choices=["schema", "values", "coverage", "checks"])
    parser.add_argument("--base", required=True, help="Baseline HF revision (tag, branch or SHA)")
    parser.add_argument("--target", required=True, help="Target HF revision")
    parser.add_argument("--max-distinct", type=int, default=100, help="values: compare columns up to this many values")
    parser.add_argument("--workers", type=int, default=8, help="Parallel footer reads")
    args = parser.parse_args()

    api = HfApi()
    target = load_revision(api, args.target, args.workers)
    base = target if args.base == args.target else load_revision(api, args.base, args.workers)
    print(f"Base {base.name}: {len(base.history)} history snapshots; target {target.name}: {len(target.history)}")
    for command in args.commands:
        match command:
            case "schema":
                cmd_schema(base, target)
            case "values":
                cmd_values(base, target, args.max_distinct)
            case "coverage":
                cmd_coverage(target)
            case "checks":
                cmd_checks(base, target)


if __name__ == "__main__":
    main()
