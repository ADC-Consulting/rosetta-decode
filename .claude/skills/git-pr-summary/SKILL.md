---
name: git-pr-summary
description: Generate a copy-paste ready PR summary in standard Markdown format. Invoked by the orchestrator before or after merging a feature branch. Never invoked by the user directly.
---

## Use for
- Generating the PR description text when the user is about to open a pull request
- Producing a consistent, copy-paste ready Markdown block every time

## Do NOT use for
- Committing (use `git-committer`)
- Pushing to remote (ask the user explicitly)
- Mid-session summaries — this is for PRs only

## Steps

### 1. Gather context

Run the following read-only commands to collect what changed on the branch:

```bash
git log main..HEAD --oneline
git diff main..HEAD --stat
```

Also read:
- `journal/SESSIONS.md` — top entry only (what was done this session)
- `journal/BACKLOG.md` — identify which backlog items were checked off on this branch

### 2. Produce the PR summary

Output exactly the following Markdown block — nothing before it, nothing after it.
The user will copy-paste this directly into the GitHub PR description.

````markdown
## {branch-name} → main

### What this PR does

{One paragraph — what the feature or change achieves and why it matters.}

### Changes

{One bold heading per logical area of change. Under each heading, bullet points — one per meaningful addition or modification. Be specific: mention file names, method names, or test counts where relevant.}

**{Area 1}**
- {change}
- {change}

**{Area 2}**
- {change}

**Tests**
- {N} new unit tests — {what they cover}
- {N} reconciliation tests (if any)
- **{N} tests total, {X}% coverage** (gate: 90%)

**Documentation**
- {doc changes, or omit section if none}

### Not in this PR
- {explicit out-of-scope items — what comes next}
````

### 3. Rules for the content

- **Branch name in the title** — use the actual git branch name, not a paraphrase
- **Past tense for done items** (`Added`, `Extended`, `Fixed`) — not future tense
- **No emojis**
- **No "this PR" self-references inside bullet points** — just state what changed
- **Tests section is always present** — even if no new tests, state the total count and coverage
- **Not in this PR section is always present** — name the next backlog items explicitly
- Keep the whole block under ~40 lines. Reviewers scan, they don't read.
