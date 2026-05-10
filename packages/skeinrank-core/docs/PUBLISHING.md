# Publishing `skeinrank` to TestPyPI and PyPI

This checklist is intentionally conservative. Publish to TestPyPI first, verify a clean install, and only then publish to the real PyPI project.

## 1. Prepare a release candidate

From the repository root:

```bash
cd packages/skeinrank-core
poetry install
poetry run pytest -q
poetry build
poetry run python -m pip install --upgrade twine
poetry run twine check dist/*
```

Expected result:

```text
Checking dist/*.tar.gz: PASSED
Checking dist/*.whl: PASSED
```

## 2. Smoke-test the built wheel locally

Use a clean virtual environment so the smoke test does not accidentally import the source checkout:

```bash
python -m venv /tmp/skeinrank-wheel-smoke
/tmp/skeinrank-wheel-smoke/bin/python -m pip install --upgrade pip
/tmp/skeinrank-wheel-smoke/bin/python -m pip install dist/*.whl
/tmp/skeinrank-wheel-smoke/bin/python -c "import skeinrank; print(skeinrank.__version__)"
/tmp/skeinrank-wheel-smoke/bin/skeinrank --help
```

Optional PDF smoke test:

```bash
/tmp/skeinrank-wheel-smoke/bin/python -m pip install pypdf
```

## 3. Publish to TestPyPI first

Use the manual GitHub Actions workflow:

```text
Actions → publish-skeinrank-core → Run workflow
repository = testpypi
dry_run = false
```

The workflow uses PyPI Trusted Publishing through `pypa/gh-action-pypi-publish`. Configure a trusted publisher for this GitHub repository in TestPyPI before running the publish step.

## 4. Install from TestPyPI in a clean environment

```bash
python -m venv /tmp/skeinrank-testpypi-smoke
/tmp/skeinrank-testpypi-smoke/bin/python -m pip install --upgrade pip
/tmp/skeinrank-testpypi-smoke/bin/python -m pip install \
  --index-url https://test.pypi.org/simple/ \
  --extra-index-url https://pypi.org/simple/ \
  skeinrank
/tmp/skeinrank-testpypi-smoke/bin/python -c "from skeinrank import load_dictionary, extract_terms; print('ok')"
/tmp/skeinrank-testpypi-smoke/bin/skeinrank --help
```

## 5. Publish to PyPI

Only after the TestPyPI install smoke test passes:

```text
Actions → publish-skeinrank-core → Run workflow
repository = pypi
dry_run = false
```

Configure a trusted publisher for the real PyPI project before running the PyPI publish step.

## Notes

- The default package remains lightweight and does not require FastAPI, SQLAlchemy, Elasticsearch, Celery, or ML dependencies.
- Install `pypdf` separately when PDF extraction is needed.
- Heavy model dependencies remain behind existing extras such as `attribute-models` and `torch`.
- Never publish directly to PyPI without a successful TestPyPI install smoke test.
