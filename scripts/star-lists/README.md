# GitHub Star Lists Organizer

Automatically categorizes your 44 starred repositories into themed **GitHub Star Lists** (the folder-like groups on your Stars page).

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

## Apply (one-time setup)

The Cursor Cloud Agent token cannot create Star Lists on your account. Run this locally with **your** GitHub auth:

```bash
# Authenticate as yourself (needs repo + read:user scopes)
gh auth login

# Preview the plan
python3 scripts/star-lists/apply-lists.py --dry-run

# Create lists and assign all starred repos
python3 scripts/star-lists/apply-lists.py
```

Or use the GitHub Action (add a `GH_TOKEN` secret with a personal access token):

1. Go to **Settings → Secrets → Actions**
2. Add `GH_TOKEN` — a [fine-grained PAT](https://github.com/settings/tokens) for `andrewjsu` with **Account permissions → Starred repositories: Read and write**
3. Run the **Organize Star Lists** workflow from the Actions tab

## Files

- `stars.jsonl` — snapshot of your starred repos (refreshed from the public API)
- `categories.json` — category rules used for bucketing
- `apply-lists.py` — creates lists via GitHub GraphQL (`createUserList`, `updateUserListsForItem`)

## Refresh stars

```bash
gh api users/andrewjsu/starred --paginate \
  --jq '.[] | {name: .full_name, id: .id, node_id: .node_id, desc: .description, lang: .language, topics: .topics, stars: .stargazers_count, archived: .archived, fork: .fork, updated: .updated_at}' \
  > scripts/star-lists/stars.jsonl
```
