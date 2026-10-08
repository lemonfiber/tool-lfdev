# Task runner for tool-lfdev. `just` with no argument lists tasks.
default:
    @just --list

# Turn on the repository's git hooks. Once per clone.
hooks:
    git config core.hooksPath .githooks

# Formatting and lint, as the `tests` job runs them.
lint:
    uvx ruff@0.16.4 format --check .
    uvx ruff@0.16.4 check .

# The suite, at 100% line and branch coverage, as the `tests` job runs it.
coverage:
    PYTHONPATH=src uvx --from coverage==7.15.2 coverage run -m unittest discover -s tests -t .
    uvx --from coverage==7.15.2 coverage report --fail-under=100

# Everything the `tests` job reads, plus spelling, which `hygiene` reads.
#
# It is not CI and does not say it is. The rest of what a pull request here
# starts is forge-side: commitlint, dco, attribution and the citation gate
# (`.githooks/commit-msg` refuses all four before the push), hygiene's
# actionlint, links, markdown, pins and shared-files, workflow-pins, CodeQL,
# gitleaks and osv-scanner.
ci: hooks lint coverage
    typos
