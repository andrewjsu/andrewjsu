#!/usr/bin/env python3
"""Create GitHub Star Lists and assign starred repos using the GraphQL API.

Requires: gh CLI authenticated as the account that owns the stars.
Run: python3 scripts/star-lists/apply-lists.py [--dry-run]
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
STARS_FILE = SCRIPT_DIR / "stars.jsonl"
CATEGORIES_FILE = SCRIPT_DIR / "categories.json"

ARCHIVED_BUCKET = "Archived"
FALLBACK_BUCKET = "Other"
REQUEST_DELAY_SEC = 1.5


@dataclass
class Category:
    name: str
    description: str = ""
    patterns: list[str] = field(default_factory=list)
    language: str | None = None

    @classmethod
    def from_dict(cls, data: dict) -> Category:
        return cls(
            name=str(data["name"]),
            description=str(data.get("description", "")),
            patterns=[str(p) for p in data.get("patterns") or []],
            language=(data.get("language") or "").lower() or None,
        )

    def matches(self, blob: str, language: str | None) -> bool:
        if self.language and language and language.lower() == self.language:
            return True
        if not self.patterns:
            return False
        for pattern in self.patterns:
            if re.search(pattern, blob):
                return True
        return False


@dataclass
class Repo:
    name: str
    node_id: str
    description: str
    language: str | None
    topics: list[str]
    archived: bool

    @classmethod
    def from_dict(cls, data: dict) -> Repo:
        return cls(
            name=str(data.get("name", "")),
            node_id=str(data.get("node_id", "")),
            description=str(data.get("desc") or data.get("description") or ""),
            language=(data.get("lang") or data.get("language") or None),
            topics=list(data.get("topics") or []),
            archived=bool(data.get("archived")),
        )

    @property
    def search_blob(self) -> str:
        return " ".join([self.name, self.description, " ".join(self.topics)]).lower()


def load_jsonl(path: Path) -> list[Repo]:
    repos: list[Repo] = []
    for line in path.read_text().splitlines():
        line = line.strip()
        if line:
            repos.append(Repo.from_dict(json.loads(line)))
    return repos


def load_categories(path: Path) -> list[Category]:
    data = json.loads(path.read_text())
    return [Category.from_dict(item) for item in data]


def categorize(repos: list[Repo], categories: list[Category]) -> dict[str, list[Repo]]:
    has_archived = any(c.name == ARCHIVED_BUCKET for c in categories)
    has_fallback = any(c.name == FALLBACK_BUCKET for c in categories)
    buckets: dict[str, list[Repo]] = {c.name: [] for c in categories}
    if not has_fallback:
        buckets[FALLBACK_BUCKET] = []

    for repo in repos:
        if repo.archived and has_archived:
            buckets[ARCHIVED_BUCKET].append(repo)
            continue

        placed = False
        for category in categories:
            if category.name == ARCHIVED_BUCKET:
                continue
            if category.matches(repo.search_blob, repo.language):
                buckets[category.name].append(repo)
                placed = True
                break

        if not placed:
            buckets[FALLBACK_BUCKET].append(repo)

    return buckets


def gh_graphql(query: str, variables: dict | None = None) -> dict:
    cmd = ["gh", "api", "graphql", "-f", f"query={query}"]
    for key, value in (variables or {}).items():
        if isinstance(value, list):
            cmd.extend(["-f", f"{key}={json.dumps(value)}"])
        elif value is not None:
            cmd.extend(["-f", f"{key}={value}"])
    result = subprocess.run(cmd, capture_output=True, text=True, check=False)
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or result.stdout.strip())
    payload = json.loads(result.stdout)
    if payload.get("errors"):
        raise RuntimeError(json.dumps(payload["errors"], indent=2))
    return payload["data"]


def get_viewer_login() -> str:
    data = gh_graphql("query { viewer { login } }")
    return data["viewer"]["login"]


def get_existing_lists() -> dict[str, dict]:
    query = """
    query($cursor: String) {
      viewer {
        lists(first: 100, after: $cursor) {
          pageInfo { hasNextPage endCursor }
          nodes { id name slug description }
        }
      }
    }
    """
    lists: dict[str, dict] = {}
    cursor: str | None = None
    while True:
        variables = {"cursor": cursor} if cursor else None
        data = gh_graphql(query, variables)
        connection = data["viewer"]["lists"]
        for node in connection["nodes"]:
            lists[node["name"].lower()] = node
        if not connection["pageInfo"]["hasNextPage"]:
            break
        cursor = connection["pageInfo"]["endCursor"]
    return lists


def create_list(name: str, description: str) -> dict:
    query = """
    mutation($name: String!, $description: String) {
      createUserList(input: {name: $name, description: $description}) {
        list { id name slug description }
      }
    }
    """
    data = gh_graphql(query, {"name": name, "description": description})
    return data["createUserList"]["list"]


def assign_repo_to_list(repo_node_id: str, list_id: str) -> None:
    query = """
    mutation($itemId: ID!, $listIds: [ID!]!) {
      updateUserListsForItem(input: {itemId: $itemId, listIds: $listIds}) {
        clientMutationId
      }
    }
    """
    gh_graphql(query, {"itemId": repo_node_id, "listIds": [list_id]})


def print_plan(buckets: dict[str, list[Repo]]) -> None:
    total = 0
    print("\nStar list plan:\n")
    for index, (name, repos) in enumerate(buckets.items(), start=1):
        if not repos:
            continue
        print(f"  {index:>2}. {name} ({len(repos)} repos)")
        total += len(repos)
    print(f"\n  Total: {total} repos across {sum(1 for r in buckets.values() if r)} lists\n")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="Preview only; do not mutate GitHub")
    args = parser.parse_args()

    repos = load_jsonl(STARS_FILE)
    categories = load_categories(CATEGORIES_FILE)
    buckets = categorize(repos, categories)
    print_plan(buckets)

    if args.dry_run:
        print("Dry run complete. Re-run without --dry-run to apply.")
        return 0

    login = get_viewer_login()
    print(f"Authenticated as: {login}")
    if login.endswith("[bot]") or login == "cursor":
        print(
            "\nThis token cannot manage your personal stars. Run locally with:\n"
            "  gh auth login\n"
            "  python3 scripts/star-lists/apply-lists.py\n"
            "\nOr add a GH_TOKEN secret and run the Organize Star Lists workflow.",
            file=sys.stderr,
        )
        return 1

    existing = get_existing_lists()
    list_ids: dict[str, str] = {}

    for category in categories:
        repos_in_bucket = buckets.get(category.name, [])
        if not repos_in_bucket or category.name in (ARCHIVED_BUCKET, FALLBACK_BUCKET):
            continue

        key = category.name.lower()
        if key in existing:
            list_ids[category.name] = existing[key]["id"]
            print(f"Using existing list: {category.name}")
            continue

        print(f"Creating list: {category.name}")
        created = create_list(category.name, category.description)
        list_ids[category.name] = created["id"]
        time.sleep(REQUEST_DELAY_SEC)

    assigned = 0
    for category_name, repos_in_bucket in buckets.items():
        if category_name in (ARCHIVED_BUCKET, FALLBACK_BUCKET) or not repos_in_bucket:
            continue
        list_id = list_ids.get(category_name)
        if not list_id:
            print(f"Skipping assignments for missing list: {category_name}", file=sys.stderr)
            continue

        for repo in repos_in_bucket:
            print(f"  -> {repo.name} => {category_name}")
            assign_repo_to_list(repo.node_id, list_id)
            assigned += 1
            time.sleep(REQUEST_DELAY_SEC)

    print(f"\nDone. Assigned {assigned} repos to {len(list_ids)} lists.")
    print(f"View at: https://github.com/{login}?tab=stars")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except RuntimeError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        raise SystemExit(1)
