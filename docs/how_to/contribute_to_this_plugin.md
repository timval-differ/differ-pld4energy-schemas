# Contribute to This Plugin

New to the code? Start with [Plugin structure](../explanation/plugin_structure.md):
the parts of the plugin, how they talk to each other, what is checked where, the
tests, and where to make a change. This page has the recipes for common changes.

## Code layout

| Module | Contents |
| --- | --- |
| `pld_deposition.py` | PLD logbooks (`PLDLogbook`, `SAPLDLogbook`, `LAPLDLogbook`), process steps, target selection, recipe loader, and the save logic (`normalize`) |
| `sps_deposition.py` | The SPS logbook (`SPSLogbook`), its process steps, plasma and target selection, and its save logic |
| `process_steps.py` | Steps shared by all systems: `GasProcessStep` (pressure, gases, valve), `HeatingStep`, `CoolDownStep` |
| `base_sections.py` | What every logbook adds to the native NOMAD process: the operator, and a name when none is given |
| `references.py` | Comparing and copying references between entries |
| `laser.py` | `LaserCalibration` (with the T1 calculation) and `LaserParameters` |
| `gas.py` | `BackgroundGas`, the gases and atmospheres |
| `stages.py` | `HeaterStagePosition`, `TargetStage`, `CartesianHeaterScan`, `PolarHeaterScan` |
| `sample.py` | System-agnostic samples: the `Sample` entry, the `SubstrateType` entry (the substrate database), `SampleInRun`, `Layer`, the `SampleRun` base of a run, `sample_id()` and `sample_name()` |
| `target.py` | `Target`, and the `PLDTarget` and `SputterTarget` database entries |
| `in_situ.py` | In-situ techniques: reading and plotting exported RHEED and MIC files, the LA-EDS energy axis |
| `composition.py` | Chemical formulas of targets and substrate types, and the elements NOMAD's search uses |
| `database.py` | The target and substrate database: the one upload that holds every target and substrate type |
| `schema_packages/schema_package.py` | Imports all modules and initialises the schema package |
| `dashboards/` | The PLD and sputter logbook dashboards, see [below](#the-logbook-dashboards) |

## Develop and test

Develop in [`nomad-distro-dev`](install_this_plugin.md#in-a-local-development-setup-nomad-distro-dev),
with the plugin in `packages/differ-pld4energy-schemas` (Python 3.10 or newer).
From the plugin folder:

```sh
uv run pytest            # all Python tests (schemas and dashboards)
uv run ruff check src tests
uv run ruff format src tests
```

The tests work from any folder (also from the distribution root). What each
test file covers is listed under [Tests and CI](../explanation/plugin_structure.md#tests-and-ci);
`tests/data/example_*.archive.yaml` are example entries, which are also tested,
and `tests/data/exports/` holds small exported data files (RHEED, MIC).

The dashboards' browser code (`dashboards/common/static/*.js`) is plain
JavaScript that the browser loads as ES modules, without a build step. It is
type-checked and tested with Node 22 or newer, also from the plugin folder:

```sh
npm ci                   # once, and after package-lock.json changes
npm run typecheck        # files that start with `// @ts-check`
npm test                 # tests/js/*.test.js
```

`npm run typecheck` uses the TypeScript version pinned in `package.json`. Only
files marked `// @ts-check` are checked, so a script is opted in once its JSDoc
types are right.

The validation rules exist in Python (`common/rules.py`) and in the page
(`common/static/rules.js`), and a parity test keeps them equal. After a
deliberate change of the rules, regenerate the expected results and check the
page's rules against them:

```sh
UPDATE_JS_PARITY=1 uv run pytest tests/dashboards/test_js_parity.py
npm test     # fails until rules.js agrees
```

In PowerShell, set the variable first:
`$env:UPDATE_JS_PARITY=1; uv run pytest tests/dashboards/test_js_parity.py; Remove-Item Env:UPDATE_JS_PARITY`.

To check an archive file with the full NOMAD processing, run from the
distribution root:

```sh
uv run nomad parse packages/differ-pld4energy-schemas/tests/data/example_sa_pld.archive.yaml
```

## Adding or changing a section

1. Define the section in the module it belongs to, using `ELNAnnotation`
   components for editable fields. Store numbers in SI units, with
   `defaultDisplayUnit` for the unit shown in the form.
2. Fields without an ELN component are read-only in the form. Use that only for
   values that are set in `normalize`, and say so in the `description`.
3. New modules must be imported in `schema_packages/schema_package.py`.
4. A new process step must inherit from the step class of its system
   (`SAPLDStep`, `LAPLDStep` or `SPSStep`), plus a shared base for its
   content, or it will not be offered in the logbook. Do not let steps of other
   systems inherit from these classes. Content shared by all systems goes in
   `process_steps.py`. Do not override an inherited quantity (e.g. `duration`)
   in a content class: with multiple inheritance the system class's version
   wins; give the quantity its own name instead.
5. Add tests and update the [reference](../reference/references.md).

### The shared schema package

All modules share one `m_package` (from `differ_pld4e_schemas/__init__.py`).
NOMAD renames a package to the module of the last section defined in it. The
GUI stores an entry's type as `<package name>.<section name>` and finds it again
by importing that module. `schema_package.py` therefore renames the package to
itself after importing everything and exposes every section there. Entry types
are then stored as
`differ_pld4e_schemas.schema_packages.schema_package.<Section>`.

`test_section_qualified_names_resolve` checks that this keeps working. If you
rename a section, entries that already use the old name no longer load.

### Save logic

`PLDLogbook.normalize` runs, in this order:

1. date default and laser details section;
2. target details: copy target info, check for duplicates;
3. samples (`SampleRun._normalize_samples`): sample IDs and names, UUIDs,
   create the Sample entries of new and external samples;
4. recipe: copy steps if `apply_recipe` is ticked;
5. step targets: fill in a single target, copy target numbers, warn about
   unselected targets.

NOMAD normalizes sub-sections before their parents, so step-level logic (scan
sub-sections, T1) has already run when the logbook's `normalize` runs.

## The logbook dashboards

Code: `src/differ_pld4e_schemas/dashboards/`. Both dashboards serve the same
page and share everything that does not depend on the system; each has its own
form definition, rules and converter.

| File | Contents |
| --- | --- |
| `pld_logbook/`, `sputter_logbook/` | One dashboard each: |
| `.../__init__.py` | Dashboard entry point |
| `.../spec.py` | Form definition, including `client`: the page's texts and settings (title, draft folder, film steps, ...) |
| `.../rules.py` | The dashboard's `LogbookRules` (film steps, systems whose steps have a sample mask, extra computed values) |
| `.../convert.py` | The dashboard's `LogbookConverter`, with the sections only it has (PLD: laser, in-situ; SPS: general comments) |
| `.../app.py` | Creates the app with `common.app.create_app` |
| `common/app.py` | FastAPI app: serves the page, `api/spec`, `api/validate`, `api/archive`, `api/draft-name`, `api/form-from-archive` |
| `common/rules.py` | `LogbookRules`: computed values, section requirements, validation, draft checks |
| `common/convert.py` | `LogbookConverter`: form ⇄ archive for run, samples, system details, targets and steps; file and draft names |
| `common/static/` | The page, no build step: `index.html`, `style.css` and ES modules: `app.js` (the page: form, NOMAD lookups, dialogs, save, drafts), `rules.js` (computed values and validation, mirroring `rules.py`), `charts.js` (plots of exported data files), `nomad-api.js` (requests to NOMAD and to the dashboard), `pdf.js` (PDF export), `dom.js` (`el()`), `config.js` (URLs), `util.js`, `constants.js` |
| `common/fields.py` | `field()`, `number()`, `comments()` |
| `common/steps.py` | Field groups of every system: gases, pressure, temperature, heating and cool-down |
| `common/values.py` | Conditions (`evaluate`), reading form values |
| `common/archive.py` | Form values ⇄ archive quantities, unit conversion |
| `common/samples.py` | The *Samples* section: fields, sample IDs and names, Sample files |

The scripts must not name a system: what differs between dashboards comes from
the spec (`client`, section intros, variant keys).

### Add or change a dashboard field

Most changes only touch `spec.py`:

```python
number(
    'spot_size',  # key in the form data
    'Spot size',  # label
    'mm^2',  # unit the user types in (pint)
    unit_label='mm²',  # how the unit is shown
    archive='laser.spot_size',  # quantity path in the schema section
    visible_if={'key': '/run/system', 'equals': 'LA-PLD'},  # optional
)
```

- The quantity must exist in the schemas; values are converted to its
  unit. `test_spec_archive_paths_exist_in_schema` checks every step field, and
  `test_spec_section_archive_paths_exist_in_schema` the other sections.
- Fields are required unless `required=False` (`textarea`, `bool`, `computed`,
  `rows` and `files` fields are optional by default).
- Choices that also exist in the schema are checked against it by
  `test_spec_choices_match_schema`.

Field kinds: `text`, `textarea`, `number`, `integer`, `select`, `bool`,
`date`, `time`, `reference` (an entry from NOMAD: a target, sample or
substrate type), `target_choice` and `sample_choice` (one of the targets or
samples of the form), `step_choice` (process steps of the form), `rows` (a
repeating sub-section, with `columns`), `files` (uploaded files, optionally with
a `chart`) and `computed`. A `reference` can copy values of the chosen entry
into the form with `ref_copy` (e.g. the material of a target), and
`required_if` makes a field required only while a condition holds.

Every field key and kind is listed in the docstring of `common/fields.py` and in
`KNOWN_KINDS` and `FIELD_KEYS` there; `tests/dashboards/test_spec_contract.py`
fails on a key or kind it does not know, so a misspelt key is caught. Add a new
key in both places.

#### Steps and sections

- A PLD step variant is made with `variant(label, sections, fields, laser=...)`:
    - `laser='required'`, `'optional'` or `'none'` says whether the step needs
      the laser. For `'optional'`, pass the keys of its laser fields in
      `laser_keys`: they get a *Laser used* switch.
    - `prefill_from='pre_ablation'` makes a new step start with the values it
      shares with the last step of that variant.
- An SPS step variant says with `target='required'` that it sputters a
  target.
- A section with `requirement={'from_steps': 'laser'}` (SPS: `'target'`) is
  required, optional or not needed depending on the steps
  (`common.rules.section_requirement`). A section that is not needed is neither
  validated nor saved.
- `count_control: True` on a list section adds a "how many" input.

If you add a new kind of field, condition, rule or computed value, implement it
in both the Python side (`common/` or the dashboard's `rules.py`) and
`common/static/rules.js`, and add tests (`tests/dashboards/`, `tests/js/`).

### Run the dashboard

- Tests: `uv run pytest tests/dashboards` and `npm test`
- In NOMAD: restart `uv run poe start` and open
  <http://localhost:8000/nomad-oasis/dashboards/differ_pld4e_schemas-pld-logbook/>
  or `.../differ_pld4e_schemas-sputter-logbook/`.
  Restart NOMAD after **any** change, to `static/` too: the page compares the
  version of its files with the one the server took when it started, and until
  a restart it asks for one instead of running against an old form definition.
- The dashboards need the target and substrate database upload
  (`database_upload_id`, see [Configuration](../explanation/plugin_structure.md#configuration)).
- A dashboard whose URL answers 404 failed to load: see
  [When the dashboard does not load](../explanation/plugin_structure.md#when-the-dashboard-does-not-load).

When you change a schema quantity the form uses (rename, unit, choices), update
`spec.py` in the same change; the dashboard tests fail until both agree.

## Git workflow

The plugin has its own repository
([timval-differ/differ-pld4energy-schemas](https://github.com/timval-differ/differ-pld4energy-schemas)),
which `nomad-distro-dev` includes as a git submodule in
`packages/differ-pld4energy-schemas`. Work in the plugin folder as in any
repository:

1. Branch from `main` (`git switch -c fix/…`).
2. Commit, with tests and the documentation in the same change, and push.
3. Open a pull request in the plugin repository. CI must pass
   (`install-and-test`, `dashboard-scripts`, `ruff-linting`).
4. After the merge, update the distribution to the new plugin commit: in the
   distribution root, `git -C packages/differ-pld4energy-schemas switch main`,
   `git -C packages/differ-pld4energy-schemas pull`, then commit the changed
   submodule pointer (`git add packages/differ-pld4energy-schemas`).

Keep each file's line endings (most files use LF): an editor or script that
changes them makes the whole file show as changed in the pull request.
