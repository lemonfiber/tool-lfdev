# tool-lfdev

`lfdev`, the lemonfiber developer command line, specified in
[`30-repos/tool-lfdev.md`](https://github.com/lemonfiber/spec/blob/main/30-repos/tool-lfdev.md).
`lfdev --help` lists the commands it has.

## Install

From a clone:

```
pip install .
lfdev --version
```

## Develop

```
just hooks      # once per clone
just ci         # lint, the suite at 100% coverage, and typos
```

## Contributing

Every change cites a requirement in the
[specification](https://github.com/lemonfiber/spec). Read the
[contributing guide](https://github.com/lemonfiber/spec/blob/main/50-governance/contributing.md)
and [AGENTS.md](AGENTS.md) before your first pull request. Report a
vulnerability privately, as
[SECURITY.md](https://github.com/lemonfiber/.github/blob/main/SECURITY.md)
describes.

## Licence

[Hippocratic License 3.0](LICENSE).
