# AGENTS.md — tool-lfdev

> **Start at the roadmap and board on [lemonfiber.app](https://lemonfiber.app),
> rendered from the report of where every unreleased version stands. Then the
> rules** every repository shares:
> [working in the repositories](https://github.com/lemonfiber/spec/blob/main/50-governance/working-in-the-repositories.md)
> and [the rules for agents](https://github.com/lemonfiber/spec/blob/main/50-governance/ai-contributors.md).
> This file holds only what is true of this repository.

## What this repository is

`lfdev`, the developer command line every contributor uses in every
repository. Spec:
[`30-repos/tool-lfdev.md`](https://github.com/lemonfiber/spec/blob/main/30-repos/tool-lfdev.md).

## Layout

```
src/lfdev/cli.py      the command line; each subcommand gets a module of its own
tests/                stdlib unittest, one file per module
```

## What is particular here

- Python's standard library only, at run time. The linter and the coverage
  tool run in CI and through `just`; nothing is installed for the tool itself.
- Every subcommand is tested, and CI holds the package at 100% line and branch
  coverage.

## Checks

```
just lint       # ruff format and check
just coverage   # the suite, at 100% line and branch coverage
just ci         # both, and typos
```
