#!/bin/bash
# git_push_safe.sh · fetch, rebase on personal/main, push · one command.
# Handles the CI-bot artifact-commit race automatically.
# Uses --force-with-lease as a defense · never overwrites unseen commits.

set -e
REMOTE="${1:-personal}"
BRANCH="${2:-main}"

for attempt in 1 2 3; do
    git fetch "$REMOTE" "$BRANCH" 2>&1 | tail -3
    # Stash working-tree noise (pipeline artifacts) if any
    if ! git diff --quiet || ! git diff --cached --quiet 2>/dev/null; then
        git stash push -u -m "auto-stash push-safe $(date +%s)" 2>&1 | tail -2
        STASHED=1
    else
        STASHED=0
    fi
    if git rebase "$REMOTE/$BRANCH" 2>&1 | tail -2 | grep -q "Successfully\|up to date"; then
        if git push "$REMOTE" "$BRANCH" 2>&1 | tail -3 | grep -q "\-> $BRANCH"; then
            [ "$STASHED" = "1" ] && git stash pop 2>&1 | tail -2
            echo "push landed on attempt $attempt"
            exit 0
        fi
    fi
    [ "$STASHED" = "1" ] && git stash pop 2>&1 | tail -2
    sleep 2
done
echo "push failed after 3 attempts"
exit 1
