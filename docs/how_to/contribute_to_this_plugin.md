# Contribute to This Plugin

## Code layout

| Module | Contents |
| --- | --- |
| `pld_deposition.py` | PLD logbooks (`PLDLogbook`, `SAPLDLogbook`, `LAPLDLogbook`), process steps, target selection, recipe loader, and the save logic (`normalize`) |
| `laser.py` | `LaserCalibration` (with the T1 calculation) and `LaserParameters` |
| `gas.py` | `BackgroundGas` |
| `stages.py` | `HeaterStagePosition`, `TargetStage`, `CartesianHeaterScan`, `PolarHeaterScan` |
| `pld_substrate.py` | `PLDSubstrate` entry, `NewSubstrate`, `sample_user_id()` |
| `target.py` | `Target` (sputter) and the `PLDTarget` entry |
| `in_situ.py` | In-situ techniques, the LA-EDS energy axis and plot |
| `sputter_deposition.py`, `source.py`, `thin_film.py`, ... | Sputter deposition schemas |
| `schema_packages/schema_package.py` | Imports all modules and initialises the schema package |
| `dashboards/pld_logbook/` | The PLD logbook dashboard, see [below](#the-pld-logbook-dashboard) |

## Develop and test

From the plugin folder:

```sh
uv run pytest            # all tests
uv run ruff check src tests
uv run ruff format src tests
```

`tests/test_pld_schema.py` covers the PLD schemas; `tests/data/example_*_pld.archive.yaml`
are example entries, which are also tested.

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
4. A new process step for a PLD system must inherit from `SAPLDStep` or
   `LAPLDStep` (plus a shared base for its content), or it will not be offered
   in the logbook. Do not let other steps inherit from these classes.
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
3. substrates: sample user ID, UUID, create the PLD Substrate entries;
4. recipe: copy steps if `apply_recipe` is ticked;
5. step targets: fill in a single target, copy target numbers, warn about
   unselected targets.

NOMAD normalizes sub-sections before their parents, so step-level logic (scan
sub-sections, T1) has already run when the logbook's `normalize` runs.

## The PLD logbook dashboard

Code: `src/differ_pld4e_schemas/dashboards/pld_logbook/`

| File | Contents |
| --- | --- |
| `__init__.py` | Dashboard entry point |
| `app.py` | FastAPI app: serves the page, `api/spec`, `api/validate`, `api/archive`, `api/form-from-archive` |
| `spec.py` | Form definition |
| `rules.py` | Conditions, computed values, validation |
| `convert.py` | Form ⇄ archive conversion |
| `static/` | Page (`index.html`, `app.js`, `style.css`), no build step |

### Add or change a dashboard field

Most changes only touch `spec.py`:

```python
number(
    'spot_size',               # key in the form data
    'Spot size',               # label
    'mm^2',                    # unit the user types in (pint)
    unit_label='mm²',          # how the unit is shown
    archive='laser.spot_size', # quantity path in the schema section
    visible_if={'key': '/run/system', 'equals': 'LA-PLD'},  # optional
)
```

- The quantity must exist in the PLD schemas; values are converted to its
  unit. `test_spec_archive_paths_exist_in_schema` checks every step field.
- Fields are required unless `required=False` (comments, booleans and computed
  fields are optional by default).
- Choices that also exist in the schema are checked against it by
  `test_spec_choices_match_schema`.

If you add a new kind of rule or computed value, implement it in both
`rules.py` and `static/app.js`, and add a test.

### Run the dashboard

- Tests: `uv run pytest tests/dashboards`
- In NOMAD: restart `uv run poe start` and open
  <http://localhost:8000/nomad-oasis/dashboards/differ_pld4e_schemas-pld-logbook/>.
  Changes to `static/` only need a browser reload; Python changes need a restart.

When you change a schema quantity the form uses (rename, unit, choices), update
`spec.py` in the same change; the dashboard tests fail until both agree.
