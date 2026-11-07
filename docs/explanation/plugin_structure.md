# Plugin structure

This page is the map of the plugin for developers: what the parts are, where
they live, how they talk to each other, what is checked where, and where to make
a change. Read it before your first change; the
[contributing guide](../how_to/contribute_to_this_plugin.md) has the recipes
for the common changes, and the [explanation](explanation.md) gives the reasons
behind the data model.

## The plugin in one picture

The plugin adds two things to NOMAD: **schemas** (the entry types of the lab's
electronic notebook) and **logbook dashboards** (guided forms that write
entries of those schemas).

```
                        ┌──────────────────────── NOMAD ────────────────────────┐
 pyproject.toml         │                                                        │
 [nomad.plugin]  ──────►│  schema package  ──►  processes archive files into     │
 entry points           │  (src/.../*.py)       entries: normalize(), search     │
                        │                                                        │
                        │  dashboards      ──►  FastAPI apps mounted at          │
                        │  (src/.../dashboards)  /dashboards/<id>/               │
                        └───────────▲───────────────────────────▲───────────────┘
                                    │ api/spec, api/archive, …   │ NOMAD API with the
                                    │ (form logic)               │ user's session:
                        ┌───────────┴────────────────────────────┴───────────────┐
                        │ browser: static/*.js — the form; writes archive files,  │
                        │ drafts and data files into the user's upload            │
                        └─────────────────────────────────────────────────────────┘
```

The dashboards never write to NOMAD themselves: the dashboard app only turns a
form into archive files (JSON), and the page writes them into an upload through
the NOMAD API, with the user's own permissions. NOMAD then processes them with
the plugin's schemas, exactly like files uploaded by hand. A logbook made with
the dashboard and one made in NOMAD's entry editor are the same kind of entry.

## Repository map

```
differ-pld4energy-schemas/
├── src/differ_pld4e_schemas/
│   ├── __init__.py              the shared metainfo package (m_package)
│   ├── schema_packages/         the schema entry point; imports every schema module
│   ├── pld_deposition.py        SA-PLD and LA-PLD logbooks, their steps and save logic
│   ├── sps_deposition.py        the SPS (sputter) logbook and its steps
│   ├── process_steps.py         steps shared by all systems (gases, heating, cool-down)
│   ├── base_sections.py         what every logbook adds to the native process (operator)
│   ├── sample.py                Sample and Substrate type entries, SampleInRun, Layer,
│   │                            sample IDs and names
│   ├── target.py                PLD and sputter target database entries
│   ├── laser.py, gas.py,        laser calibration, background gases,
│   │   stages.py                heater and target stages
│   ├── in_situ.py               in-situ techniques; reads and plots exported data files
│   ├── composition.py,          chemical formulas → elements (native search),
│   │   database.py,             the target and substrate database upload,
│   │   references.py            comparing and copying references
│   └── dashboards/
│       ├── __init__.py          the two dashboard entry points
│       ├── pld_logbook/         PLD dashboard: spec.py, rules.py, convert.py, app.py
│       ├── sputter_logbook/     sputter dashboard: the same four files
│       └── common/              everything the dashboards share
│           ├── app.py           the FastAPI app (create_app) and its endpoints
│           ├── fields.py        building blocks of a form definition (field(), …)
│           ├── values.py        conditions, numbers, dates, step times
│           ├── rules.py         LogbookRules: computed values and validation
│           ├── samples.py       the Samples section and the Sample files
│           ├── archive.py       form values ⇄ archive quantities (units)
│           ├── convert.py       LogbookConverter: form ⇄ archive files
│           ├── steps.py         field groups every system has
│           └── static/          the page (HTML, CSS, ES modules), no build step
├── tests/
│   ├── test_*.py                the schemas (Python)
│   ├── schema_packages/         the schema package loads
│   ├── dashboards/              the dashboards (Python)
│   ├── js/                      the page's scripts (Node), fixtures/parity.json
│   └── data/                    example archives; exports/ (small RHEED and MIC files)
├── docs/, mkdocs.yml            this documentation
├── package.json, jsconfig.json  type checking and tests of the scripts (dev only)
├── pyproject.toml               package, dependencies, entry points, ruff, pytest
├── .github/                     CI, docs deployment, Dependabot
├── .gitattributes               test exports are kept byte for byte
├── .devcontainer/               a Python and Node container for the plugin alone
│                                (no NOMAD services), see "Tests and CI"
└── nomad.yaml, .cruft.json,     left from the plugin template: not used by the
    move_template_files.sh,      distribution (its configuration is the nomad.yaml
    MANIFEST.in                  at the distribution root)
```

## Part 1: the schemas

Each entry type is a section class that extends a native NOMAD section (e.g.
`PulsedLaserDeposition`, `CompositeSystem`), so NOMAD's search finds entries by
method, elements and lab ID; see [Search](explanation.md#search).

- **One package.** All modules define their sections in one metainfo package
  (`differ_pld4e_schemas/__init__.py`); `schema_packages/schema_package.py`
  imports every module and gives the package its final name. Entry types are
  stored as `differ_pld4e_schemas.schema_packages.schema_package.<Section>`, so
  renaming a section breaks existing entries
  ([why](../how_to/contribute_to_this_plugin.md#the-shared-schema-package)).
- **Save logic** lives in `normalize()` of the sections: sample IDs and names,
  creating Sample entries, copying target details, applying recipes, filling
  the native search sections. NOMAD normalizes sub-sections before their
  parents.
- **Systems** are kept apart by class hierarchy: a step must inherit from its
  system's step class (`SAPLDStep`, `LAPLDStep`, `SPSStep`) to be offered in
  that logbook; shared content lives in base classes and `process_steps.py`.
- **Exported data files** (RHEED, MIC) are read in `in_situ.py`. Instrument
  exports come in several encodings (the MIC export has a Latin-1 header), so
  they are read as bytes and decoded per line (`text_lines`).

## Part 2: the dashboards

### The server: one FastAPI app per dashboard

`dashboards/<name>/app.py` calls `common.app.create_app(form_spec, rules,
converter)` with the dashboard's own three parts:

| Part | File | What it is |
| --- | --- | --- |
| Form definition (spec) | `<name>/spec.py` | Every section and field of the form: kind, unit, schema path (`archive`), choices, when it is shown (`visible_if`) and required. Its `client` part holds the page's texts and settings. |
| Rules | `<name>/rules.py` | A `LogbookRules`: which steps grow films, on which samples, extra computed values. |
| Converter | `<name>/convert.py` | A `LogbookConverter`, plus the sections only this dashboard has (PLD: laser, in-situ). |

The app serves:

| Endpoint | Does |
| --- | --- |
| `GET /` | The page, with every linked static file versioned by its content (`?v=`). |
| `GET /static/<file>` | The page's files, always revalidated by the browser (`Cache-Control: no-cache`, 304 while unchanged). |
| `GET /api/spec` | The form definition, plus `script_version` (a hash of all static files): when the page and the running server disagree, the page asks for a restart of NOMAD. |
| `POST /api/validate` | Errors and warnings of a form (the page checks locally; used by tests). |
| `POST /api/archive` | Validates again, then returns the archive files to write: one per new or external sample, then the logbook. |
| `POST /api/draft-name` | Where a draft of the form is kept in the upload. |
| `POST /api/form-from-archive` | A saved logbook (or a recipe) read back into a form. |

No request is answered with a 500. A body that does not fit the request model
(e.g. `form` is not an object) gets FastAPI's **422**; a form whose content has
an unexpected shape gets **400 "Malformed form: …"** where reading it fails, or
a 200 that lists the problems where validation catches them.

### The form definition is the contract

The spec is plain data (dicts and lists) that both sides read: Python validates
and converts with it, the page renders the form from it. Nothing types it, so
`tests/dashboards/test_spec_contract.py` checks every field kind and key
(`KNOWN_KINDS`, `FIELD_KEYS` in `common/fields.py`), every condition, the
sections and the computed values of both dashboards. When you introduce a
key:

- a **field** key or kind: add it to `KNOWN_KINDS`/`FIELD_KEYS` and the
  docstring of `common/fields.py`;
- a **section** or **step variant** key (like `requirement`, `count_control`,
  `prefill_from`, `laser`): add it to `SECTION_KEYS`/`VARIANT_KEYS` in
  `test_spec_contract.py` and to the docstring of `pld_logbook/spec.py`, which
  documents them.

### The page: ES modules without a build step

The browser loads the files in `common/static/` as they are: `index.html` loads
`app.js` as an ES module, which imports the others. There is no bundler and no
transpiler; Node is only used to type-check and test them.

| Module | What | Uses |
| --- | --- | --- |
| `app.js` | The page: start page, form rendering, NOMAD lookups, dialogs, save, drafts, PDF report. Holds the page's state in one `app` object. | `rules.js`, `charts.js`, `nomad-api.js`, `pdf.js`, `config.js`, `dom.js`, `util.js` |
| `rules.js` | Computed values and validation, the counterpart of `rules.py` (`createRules(ctx)` reads `ctx.spec` and `ctx.refs` when a rule runs). | `constants.js`, `util.js` |
| `charts.js` | Reading and plotting exported data files. | `dom.js`, `util.js` |
| `nomad-api.js` | Requests to NOMAD (with the session cookie) and to the dashboard's API. | `config.js`, `util.js` |
| `pdf.js` | A small PDF writer for the report (the sandboxed frame ignores `window.print()`). | – |
| `config.js` | URLs from the page's location: `API`, `GUI`, `DASHBOARD`. | – |
| `dom.js` | `el()`: elements built in code, never from HTML strings. | – |
| `util.js`, `constants.js` | Stateless helpers (dates, file names, upload paths), and values mirrored from Python (`NEW_SAMPLE`, `MADE_HERE`, `LEVELS`; `test_page_constants_match_python` checks them). | – |

Rules for the scripts:

- They never name a system or dashboard: what differs comes from the spec.
- Modules other than `app.js` have no state of their own; they get what they
  need as arguments (see `renderFileCharts`).
- A file is type-checked once it starts with `// @ts-check` (all but `app.js`
  so far), using JSDoc types.
- NOMAD shows the dashboard in a sandboxed frame without `allow-modals`:
  `window.confirm/alert/prompt/print` do nothing, so the page has its own
  dialogs and makes PDFs itself (a test enforces this).

### The rules exist twice, and must agree

The page checks the form while you type (`rules.js`); the server checks it
again before it builds anything (`rules.py`). Python is the reference: it
decides what is saved. `tests/dashboards/test_js_parity.py` runs about 90 forms
of both dashboards through the Python rules and keeps the results in
`tests/js/fixtures/parity.json`; `tests/js/parity.test.js` requires `rules.js`
to give the same errors, warnings, draft errors and computed values. After a
deliberate change of the rules:

```sh
UPDATE_JS_PARITY=1 uv run pytest tests/dashboards/test_js_parity.py
npm test     # fails until rules.js agrees
```

In PowerShell, set the variable first:
`$env:UPDATE_JS_PARITY=1; uv run pytest tests/dashboards/test_js_parity.py; Remove-Item Env:UPDATE_JS_PARITY`.

One check is deliberately browser-only: an existing sample whose sample ID is
also that of a sample made in the run (the server does not look samples up).

### What happens when a logbook is saved

```
page                                   dashboard app                NOMAD API
 │ validate locally (rules.js)
 │ ─ POST api/archive {form, logbook_file} ──►  validate (rules.py)
 │                                               build files (convert.py)
 │ ◄──────────── files, logbook_file, warnings ─┘
 │ upload new data files ─────────────────────────────────────────►  PUT raw/<file_dir>/<run>/…
 │ (again api/archive, now with the uploaded file paths)
 │ for each file (samples first, then the logbook) ───────────────►  PUT raw/?file_name=…
 │                                                                     &overwrite_if_exists=…
 │                                                                     &wait_for_processing=true
 │ show NOMAD's processing errors and warnings; delete the draft ──►  DELETE raw/<draft>
```

`<file_dir>` and `<draft_dir>` come from the `client` part of the spec
(`pld_files`/`pld_drafts` for PLD, `sps_files`/`sps_drafts` for SPS). Data files
and drafts are written with `wait_for_processing=false`: NOMAD does not process
them into entries. Drafts are the form state as `<draft_dir>/<run>.draft.json`;
no parser reads them, so they are never entries (see
[Drafts](explanation.md#drafts)).

### Configuration

| Setting | Where | What |
| --- | --- | --- |
| `database_upload_id` | `nomad.yaml` at the distribution root (or of the Oasis), under the options of `differ_pld4e_schemas.schema_packages:schema_package_entry_point` | The upload that holds the target and substrate database. Without it the dashboards cannot offer targets or substrates. See [Set up the target and substrate database](../how_to/use_this_plugin.md#set-up-the-target-and-substrate-database). The tests set a placeholder (`tests/conftest.py`). |
| `dashboards.enabled` | NOMAD's `nomad.yaml` | Dashboards are on by default; with `false` NOMAD serves none. |
| `dashboards.frame_ancestors` | NOMAD's `nomad.yaml` | Origins allowed to show the dashboards in a frame (default: NOMAD itself). Add the origin of another GUI, e.g. the GUI development server, to embed them there. |

The option `database_upload_id` is defined on the schema entry point
(`schema_packages/__init__.py`) and read by `database.py`, which passes it into
the form definition of both dashboards.

### When the dashboard does not load

- NOMAD mounts each dashboard when it starts. If a dashboard fails to load
  (an exception in its `spec.py`, `rules.py` or `convert.py`), NOMAD logs an
  error that names the entry point, skips that dashboard, and its URL answers
  404. Look for that error in NOMAD's log.
- The page compares a version of its files with the version the running server
  took at its start. After any change to `static/` or to Python, restart NOMAD
  (`uv run poe start`); until then the page shows "The dashboard was updated,
  but NOMAD still runs the previous version of it".

### What is trusted, and what is checked

The page runs with the user's own NOMAD permissions, so NOMAD decides which
uploads a user can write to. Within that, drafts are files in uploads that
co-authors can change, and the server cannot see which upload the page writes
to, so both sides check:

| Risk | Checked by |
| --- | --- |
| A draft that sends the save into another upload | The page: `checkedEdit` keeps a draft's logbook only if it is in the draft's own upload and has a name the dashboard makes; checked again before every save. |
| Overwriting a file that is not the opened logbook | The server: `is_logbook_file` (`common/convert.py`) allows only `{system}_{date}_{hhmm}[_{name}].archive.json`; anything else is saved as a new logbook. |
| Overwriting another sample's file | The server: `own_sample_file` (`common/samples.py`) allows a Sample file only if it is the file of that sample's ID; else the link is kept and a warning shown. |
| Paths that leave the upload or change the request | The page: `uploadPath` (`util.js`) checks the upload id and encodes every part. |
| Forms of the wrong shape | The server: 400 or 422 instead of 500 (`malformed_request` in `common/app.py`). |
| Injected HTML | The page builds every element with `el()` and text nodes; there is no `innerHTML`. |

## Tests and CI

| Tests | Cover |
| --- | --- |
| `tests/test_pld_schema.py`, `test_sputter_schema.py` | The schemas: sections, save logic, recipes, exported data files. |
| `tests/test_database.py`, `test_native_search.py` | The target and substrate database; the native sections NOMAD searches. |
| `tests/schema_packages/` | The schema package loads, with an example entry. |
| `tests/dashboards/test_pld_logbook.py`, `test_sputter_logbook.py` | Each dashboard: spec against the schemas, validation, conversion, the app. |
| `tests/dashboards/test_spec_contract.py` | The form definitions' keys, kinds, conditions and computed values. |
| `tests/dashboards/test_js_parity.py` | Writes and checks `tests/js/fixtures/parity.json`. |
| `tests/dashboards/test_dashboard_input.py` | Which files a save may overwrite. |
| `tests/dashboards/test_malformed_input.py` | Malformed requests get a 400, 422 or a 200 listing the problems, never a 500. |
| `tests/dashboards/test_page.py` | The page, versioned and revalidated static files, no blocked dialogs. |
| `tests/js/*.test.js` | The scripts: `rules`, `parity`, `charts`, `nomad-api`, `pdf`. |

Test data: `tests/data/example_*.archive.yaml` are example entries;
`tests/data/exports/` holds small RHEED and MIC exports, kept byte for byte
(`.gitattributes`). `tests/data/raw_data/` is for large local files and is not
in the repository.

Run everything from the plugin folder. In the distribution, `uv` uses the
distribution's environment. For the plugin repository on its own (e.g. in the
devcontainer, which has Python and Node but not uv), install
[uv](https://docs.astral.sh/uv/) and run `uv sync --all-extras` in the plugin
folder first, as CI does.


```sh
uv run pytest                 # Python: schemas and dashboards
uv run ruff check src tests
npm ci && npm run typecheck && npm test    # the page's scripts (Node 22+)
```

CI (`.github/workflows/actions.yml`) runs on every push and pull request:
`install-and-test` (pytest with coverage), `dashboard-scripts` (type check and
JS tests) and `ruff-linting` (`ruff check .` on the whole repository, so run
`uv run ruff check .` locally to see the same). Note that CI installs the newest `nomad-lab`
without its infrastructure extras: NOMAD then logs with the standard `logging`
module instead of structlog, which tests that check log messages must allow for.
`mkdocs-deploy.yml` publishes this documentation on every push to `main`.
Dependabot proposes updates of the GitHub Actions, npm and devcontainer
dependencies weekly.

## Conventions

- **Units.** Archives store SI units; forms show lab units. A form field's
  `unit` is converted to the schema quantity's unit with pint (`archive.py`).
- **Python is the reference** for rules shared with the page.
- **No build step** for the page, and no runtime dependencies in it.
- **Line endings.** Keep a file's line endings (most files use LF); a change of
  line endings makes the whole file show as changed.
- **Tests come with changes**: Python tests in `tests/`, JS tests in
  `tests/js/`, the parity fixture regenerated when the rules change.

## Where do I change …?

| I want to … | Change | See |
| --- | --- | --- |
| add a field to an entry type | the section in its module; `docs/reference` | [Adding or changing a section](../how_to/contribute_to_this_plugin.md#adding-or-changing-a-section) |
| show a schema field in a dashboard | `<name>/spec.py` | [Add or change a dashboard field](../how_to/contribute_to_this_plugin.md#add-or-change-a-dashboard-field) |
| add a process step type | the schema module (step class of its system) and `spec.py` (a variant) | [Steps and sections](../how_to/contribute_to_this_plugin.md#steps-and-sections) |
| add a computed value | the dashboard's `rules.py` (`extra_computed`) and `COMPUTED` in `static/rules.js`; regenerate the parity fixture | [The rules exist twice](#the-rules-exist-twice-and-must-agree) |
| add a field kind or a field key | `common/fields.py` (`KNOWN_KINDS`, `FIELD_KEYS`, docstring), `values.py`/`rules.py`, `static/rules.js` and `app.js` (rendering) | [The form definition is the contract](#the-form-definition-is-the-contract) |
| add a section or step variant key | `pld_logbook/spec.py` (docstring), `SECTION_KEYS`/`VARIANT_KEYS` in `tests/dashboards/test_spec_contract.py`, and the code that reads it | [The form definition is the contract](#the-form-definition-is-the-contract) |
| set up the database upload, or turn dashboards off | `nomad.yaml` at the distribution root | [Configuration](#configuration) |
| change validation | `common/rules.py` and `static/rules.js`; regenerate the parity fixture | [The rules exist twice](#the-rules-exist-twice-and-must-agree) |
| change what is saved | `common/convert.py` (or the dashboard's `convert.py`), `common/samples.py` | [What happens when a logbook is saved](#what-happens-when-a-logbook-is-saved) |
| change the page | `static/app.js`, or the module the code belongs to | [The page](#the-page-es-modules-without-a-build-step) |
| plot a new kind of data file | the field's `chart` in `spec.py`; reading in `in_situ.py` and `static/charts.js` | `FILE_CHARTS` in `pld_logbook/spec.py` |
| add a dashboard for another system | a new folder like `sputter_logbook/` (spec, rules, convert, app, `__init__.py` with the entry point), export the entry point from `dashboards/__init__.py`, and register it under `[project.entry-points."nomad.plugin"]` in `pyproject.toml` | `dashboards/__init__.py` |
| change the docs | `docs/`, `mkdocs.yml` | [Contribute to the documentation](../how_to/contribute_to_the_documentation.md) |
