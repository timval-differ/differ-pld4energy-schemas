# Contribute to This Plugin

## Code layout

| Module | Contents |
| --- | --- |
| `pld_deposition.py` | PLD logbooks (`PLDLogbook`, `SAPLDLogbook`, `LAPLDLogbook`), process steps, target selection, recipe loader, and the save logic (`normalize`) |
| `laser.py` | `LaserCalibration` (with the T1 calculation) and `LaserParameters` |
| `gas.py` | `BackgroundGas`, the gases and atmospheres |
| `stages.py` | `HeaterStagePosition`, `TargetStage`, `SubstrateStageScan`, `CartesianHeaterScan`, `PolarHeaterScan` |
| `sample.py` | System-agnostic samples: the `Sample` entry, `SampleInRun`, `Layer`, the `SampleRun` base of a run, `sample_id()` and `sample_name()` |
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
3. samples (`SampleRun._normalize_samples`): sample IDs and names, UUIDs,
   create the Sample entries of new and external samples;
4. recipe: copy steps if `apply_recipe` is ticked;
5. step targets: fill in a single target, copy target numbers, warn about
   unselected targets.

NOMAD normalizes sub-sections before their parents, so step-level logic (scan
sub-sections, T1) has already run when the logbook's `normalize` runs.

## The PLD logbook dashboard

Code: `src/differ_pld4e_schemas/dashboards/pld_logbook/`, with the parts that
do not depend on PLD in `src/differ_pld4e_schemas/dashboards/common/`, for
reuse by a sputter logbook dashboard.

| File | Contents |
| --- | --- |
| `pld_logbook/__init__.py` | Dashboard entry point |
| `pld_logbook/app.py` | FastAPI app: serves the page, `api/spec`, `api/validate`, `api/archive`, `api/draft-name`, `api/form-from-archive` |
| `pld_logbook/spec.py` | Form definition |
| `pld_logbook/rules.py` | Computed values, section requirements, validation, draft checks |
| `pld_logbook/convert.py` | Form ⇄ archive conversion, file and draft names |
| `pld_logbook/static/` | Page (`index.html`, `app.js`, `style.css`), no build step |
| `common/fields.py` | `field()`, `number()`, `comments()` |
| `common/values.py` | Conditions (`evaluate`), reading form values |
| `common/archive.py` | Form values ⇄ archive quantities, unit conversion |
| `common/samples.py` | The *Samples* section: fields, sample IDs and names, Sample files |

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
  unit. `test_spec_archive_paths_exist_in_schema` checks every step field, and
  `test_spec_section_archive_paths_exist_in_schema` the other sections.
- Fields are required unless `required=False` (comments, booleans and computed
  fields are optional by default).
- Choices that also exist in the schema are checked against it by
  `test_spec_choices_match_schema`.

Field kinds: `text`, `textarea`, `number`, `integer`, `select`, `bool`,
`date`, `time`, `reference` (an entry from NOMAD), `target_choice` and
`sample_choice` (one of the targets or samples of the form), `material_choice`
(a material from the target database), `rows` (a repeating sub-section, with
`columns`), `file` and `computed`.

#### Steps and sections

- A step variant is made with `variant(label, sections, fields, laser=...)`:
    - `laser='required'`, `'optional'` or `'none'` says whether the step needs
      the laser. For `'optional'`, pass the keys of its laser fields in
      `laser_keys`: they get a *Laser used* switch.
    - `prefill_from='pre_ablation'` makes a new step start with the values it
      shares with the last step of that variant.
- A section with `requirement={'from_steps': 'laser'}` is required, optional
  or not needed depending on the steps (`rules.section_requirement`). A section
  that is not needed is neither validated nor saved.
- `count_control: True` on a list section adds a "how many" input.

If you add a new kind of field, condition, rule or computed value, implement it
in both the Python side (`common/` or `rules.py`) and `static/app.js`, and add a
test.

### Run the dashboard

- Tests: `uv run pytest tests/dashboards`
- In NOMAD: restart `uv run poe start` and open
  <http://localhost:8000/nomad-oasis/dashboards/differ_pld4e_schemas-pld-logbook/>.
  Changes to `static/` only need a browser reload; Python changes need a restart.

When you change a schema quantity the form uses (rename, unit, choices), update
`spec.py` in the same change; the dashboard tests fail until both agree.
