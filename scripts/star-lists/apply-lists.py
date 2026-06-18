#!/usr/bin/env python3
"""Create GitHub Star Lists and assign starred repos using the GraphQL API.

Requires: gh CLI authenticated as the account that owns the stars, or GH_TOKEN.
Run from the repo root:
  python scripts/star-lists/apply-lists.py --dry-run
  python scripts/star-lists/apply-lists.py
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
STARS_FILE = SCRIPT_DIR / "stars.jsonl"
CATEGORIES_FILE = SCRIPT_DIR / "categories.json"
GRAPHQL_URL = "https://api.github.com/graphql"

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


def die(message: str) -> None:
    print(f"Error: {message}", file=sys.stderr)
    raise SystemExit(1)


def require_files() -> None:
    missing = [path for path in (STARS_FILE, CATEGORIES_FILE) if not path.is_file()]
    if not missing:
        return
    die(
        "Missing required files:\n"
        + "\n".join(f"  - {path}" for path in missing)
        + "\n\nMake sure you are in the andrewjsu repo and on a branch that includes "
        "scripts/star-lists/ (merge PR #1 or run: git checkout cursor/organize-starred-repos-7d7e)."
    )


def load_jsonl(path: Path) -> list[Repo]:
    repos: list[Repo] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            repos.append(Repo.from_dict(json.loads(line)))
    if not repos:
        die(f"No starred repos found in {path}. Run with --refresh first.")
    return repos


def load_categories(path: Path) -> list[Category]:
    data = json.loads(path.read_text(encoding="utf-8"))
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


def get_token() -> str:
    token = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")
    if token:
        return token.strip()

    result = subprocess.run(
        ["gh", "auth", "token"],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode == 0 and result.stdout.strip():
        return result.stdout.strip()

    die(
        "No GitHub token found.\n"
        "Run: gh auth login\n"
        "Or set GH_TOKEN to a personal access token."
    )


def graphql(token: str, query: str, variables: dict | None = None) -> dict:
    payload = {"query": query}
    if variables is not None:
        payload["variables"] = variables

    request = urllib.request.Request(
        GRAPHQL_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"bearer {token}",
            "Content-Type": "application/json",
            "User-Agent": "andrewjsu-star-organizer",
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            body = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        die(f"GitHub API HTTP {exc.code}: {detail}")
    except urllib.error.URLError as exc:
        die(f"Network error talking to GitHub: {exc.reason}")

    if body.get("errors"):
        messages = [err.get("message", json.dumps(err)) for err in body["errors"]]
        die("GitHub GraphQL error:\n" + "\n".join(f"  - {msg}" for msg in messages))

    return body["data"]


def get_viewer_login(token: str) -> str:
    data = graphql(token, "query { viewer { login } }")
    return data["viewer"]["login"]


def get_existing_lists(token: str) -> dict[str, dict]:
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
        variables = {"cursor": cursor}
        data = graphql(token, query, variables)
        connection = data["viewer"]["lists"]
        for node in connection["nodes"]:
            lists[node["name"].lower()] = node
        if not connection["pageInfo"]["hasNextPage"]:
            break
        cursor = connection["pageInfo"]["endCursor"]
    return lists


def create_list(token: str, name: str, description: str) -> dict:
    query = """
    mutation($name: String!, $description: String) {
      createUserList(input: {name: $name, description: $description}) {
        list { id name slug description }
      }
    }
    """
    data = graphql(token, query, {"name": name, "description": description})
    created = data["createUserList"]["list"]
    if not created:
        die(f"GitHub did not return a list for {name!r}. Check token scopes.")
    return created


def assign_repo_to_list(token: str, repo_node_id: str, list_id: str) -> None:
    query = """
    mutation($itemId: ID!, $listIds: [ID!]!) {
      updateUserListsForItem(input: {itemId: $itemId, listIds: $listIds}) {
        clientMutationId
      }
    }
    """
    graphql(token, query, {"itemId": repo_node_id, "listIds": [list_id]})


def refresh_stars(token: str, username: str) -> None:
    cmd = [
        "gh",
        "api",
        f"users/{username}/starred",
        "--paginate",
        "--jq",
        ".[] | {name: .full_name, id: .id, node_id: .node_id, desc: .description, "
        "lang: .language, topics: .topics, stars: .stargazers_count, "
        "archived: .archived, fork: .fork, updated: .updated_at}",
    ]
    env = os.environ.copy()
    env["GH_TOKEN"] = token
    result = subprocess.run(cmd, capture_output=True, text=True, check=False, env=env)
    if result.returncode != 0:
        die(result.stderr.strip() or result.stdout.strip() or "Failed to refresh starred repos.")

    lines = [line for line in result.stdout.splitlines() if line.strip()]
    if not lines:
        die(f"No starred repos returned for {username}.")

    STARS_FILE.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"Refreshed {len(lines)} starred repos into {STARS_FILE}")


def print_plan(buckets: dict[str, list[Repo]]) -> None:
    total = 0
    list_count = 0
    print("\nStar list plan:\n")
    for index, (name, repos) in enumerate(buckets.items(), start=1):
        if not repos:
            continue
        list_count += 1
        print(f"  {index:>2}. {name} ({len(repos)} repos)")
        total += len(repos)
    print(f"\n  Total: {total} repos across {list_count} lists\n")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="Preview only; do not change GitHub")
    parser.add_argument("--refresh", action="store_true", help="Refresh stars.jsonl from GitHub first")
    parser.add_argument("--username", default="andrewjsu", help="GitHub username (default: andrewjsu)")
    args = parser.parse_args()

    require_files()

    token: str | None = None
    if args.refresh or not args.dry_run:
        token = get_token()

    if args.refresh:
        assert token is not None
        refresh_stars(token, args.username)

    repos = load_jsonl(STARS_FILE)
    categories = load_categories(CATEGORIES_FILE)
    buckets = categorize(repos, categories)
    print_plan(buckets)

    if args.dry_run:
        print("Dry run complete. Re-run without --dry-run to create lists on GitHub.")
        return 0

    assert token is not None
    login = get_viewer_login(token)
    print(f"Authenticated as: {login}")
    if login.lower() != args.username.lower():
        print(
            f"Warning: logged in as {login}, but organizing stars for {args.username}.",
            file=sys.stderr,
        )

    existing = get_existing_lists(token)
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
        created = create_list(token, category.name, category.description)
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
            if not repo.node_id:
                die(f"Missing node_id for {repo.name}. Re-run with --refresh.")
            print(f"  -> {repo.name} => {category_name}")
            assign_repo_to_list(token, repo.node_id, list_id)
            assigned += 1
            time.sleep(REQUEST_DELAY_SEC)

    print(f"\nDone. Assigned {assigned} repos to {len(list_ids)} lists.")
    print(f"View at: https://github.com/{args.username}?tab=stars")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        print("\nCancelled.", file=sys.stderr)
        raise SystemExit(130)
