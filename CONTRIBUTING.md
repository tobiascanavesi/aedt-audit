# Contributing

Thanks for your interest in improving `aedt-audit`.

## Ground rules

- **Scope is intentionally narrow:** metrics and report formats defined by
  statute, regulation, or federal guidance (LL144/DCWP, EEOC Uniform
  Guidelines, NIST AI RMF). PRs adding scoring, ranking, or candidate-matching
  logic will be declined — that is out of scope by design.
- **Every legal formula needs a hand-computed fixture.** If your change touches
  a rate, ratio, or threshold, include a test where the expected value is
  computed by hand in a comment, with the legal citation.
- **No real applicant data, ever** — not in tests, fixtures, examples, or
  issues. Use `aedt_audit.synth`.

## Development setup

```bash
git clone https://github.com/tobiascanavesi/aedt-audit && cd aedt-audit
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
ruff check src tests && pytest
```

## The web app

`web/index.html` runs the package in the browser with Pyodide; GitHub Pages
publishes it together with a wheel built from `main` (`.github/workflows/pages.yml`).
To test it locally against your working copy:

```bash
python -m build --wheel --outdir dist
cp dist/*.whl web/ && printf '{"wheel": "%s"}' "$(basename dist/*.whl)" > web/wheel.json
python -m http.server 8788 -d web      # then open http://127.0.0.1:8788/
```

The wheel and `wheel.json` are git-ignored. Without them the page installs the
published release from PyPI instead.

## Pull requests

- One logical change per PR, with a clear description of the *legal basis* for
  any behavioral change (cite the rule section).
- CI must pass: ruff + pytest on Python 3.10–3.14, plus a minimum-pins job at
  the oldest supported pandas/numpy (1.5 / 1.23 on Python 3.10).
- The package version lives in `src/aedt_audit/__init__.py` (`__version__`);
  `pyproject.toml` reads it from there. Add a line to `CHANGELOG.md`.
