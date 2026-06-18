# GitHub Star Lists Organizer

Automatically categorizes your 44 starred repositories into themed **GitHub Star Lists** (the folder-like groups on your Stars page).

## Quick start

From the **repo root** (`andrewjsu`), after merging this branch:

### Windows

```cmd
gh auth login
scripts\star-lists\organize-stars.cmd --dry-run
scripts\star-lists\organize-stars.cmd
```

### Mac / Linux

```bash
gh auth login
bash scripts/star-lists/organize-stars.sh --dry-run
bash scripts/star-lists/organize-stars.sh
```

### Any OS (direct)

```bash
gh auth login
python scripts/star-lists/apply-lists.py --dry-run
python scripts/star-lists/apply-lists.py
```

Use `python` instead of `python3` on Windows if `python3` is not recognized.

## Troubleshooting

**"Missing required files"** — You are not in the repo, or this branch is not checked out. Run:

```bash
git fetch origin
git checkout cursor/organize-starred-repos-7d7e
```

Or merge [PR #1](https://github.com/andrewjsu/andrewjsu/pull/1) into `main` and pull.

**"No GitHub token found"** — Run `gh auth login` and complete the browser flow. Verify with:

```bash
gh auth status
gh api user -q .login
```

**"Resource not accessible" / GraphQL forbidden** — Your token needs permission to manage starred repos. For classic PATs, include scope `repo`. For fine-grained PATs, enable **Account → Starred repositories: Read and write**.

**Refresh stars before applying:**

```bash
python scripts/star-lists/apply-lists.py --refresh --dry-run
python scripts/star-lists/apply-lists.py --refresh
```

## Categories

| List | Repos | Theme |
|------|------:|-------|
| Agent Skills & Frameworks | 9 | Claude Code skills, harnesses, IDE rules |
| CLI & Dev Tools | 7 | CLIs, git worktrees, dev utilities |
| OpenClaw & Hermes | 6 | OpenClaw / Hermes / gstack ecosystem |
| AI Agents & Orchestration | 6 | Multi-agent orchestration and harnesses |
| Auto-Research | 4 | Autonomous research and self-improving loops |
| Memory & Context | 3 | Agent memory layers and context hubs |
| Learning & Reference | 3 | Awesome lists, APIs, tutorials |
| Voice & Audio AI | 2 | Voice cloning and speech-to-text |
| UI & Content Tools | 2 | Editors and text layout |
| Code Intelligence | 1 | Codebase knowledge graphs |
| Web Research | 1 | Cross-platform social/web research |

## GitHub Action (no local Python needed)

1. Merge this PR
2. Add repo secret `GH_TOKEN` — fine-grained PAT with **Starred repositories: Read and write**
3. **Actions → Organize Star Lists → Run workflow** → set `dry_run: false`

## Files

- `stars.jsonl` — snapshot of starred repos
- `categories.json` — category rules
- `apply-lists.py` — creates lists via GitHub GraphQL
- `organize-stars.cmd` / `organize-stars.sh` — wrappers that pick the right Python command
