# git-branch-setup

## Use for
- Before coding begins on any new feature
- Ensuring the correct feature branch exists and is checked out before any implementation is delegated

## Do NOT use for
- Hotfixes or ad-hoc commits on the current branch
- Mid-feature work where the branch already exists and is active

## Steps

1. Determine the expected branch name for the feature being implemented. Convention is `feat/F<N>-<slug>` (e.g. `feat/F3-llm-upgrade`). Derive it from the active plan file name (`docs/plans/F<N>-<slug>.md`) or ask the user to confirm if ambiguous.

2. Run `git branch --list <branch-name>` to check if the branch exists locally.

3. Run `git ls-remote --heads origin <branch-name>` to check if it exists on the remote.

4. Decision table:
   - Branch exists locally AND is already checked out → report "Already on <branch-name>, nothing to do." and stop.
   - Branch exists locally but NOT checked out → run `git checkout <branch-name>` and report.
   - Branch does NOT exist locally but exists on remote → run `git checkout --track origin/<branch-name>` and report.
   - Branch does NOT exist anywhere → follow steps 4a–4c below to create it cleanly off main.

4a. Switch to main: `git checkout main`

4b. Pull latest from remote: `git pull origin main`

4c. Create and switch to the new branch: `git checkout -b <branch-name>`. Report the new branch name to the user.

5. After switching, confirm the active branch with `git branch --show-current` and report it to the user before continuing.

6. Never force-push, delete, or reset any branch. If an unexpected state is found (e.g. diverged history, detached HEAD), stop and ask the user how to proceed.
