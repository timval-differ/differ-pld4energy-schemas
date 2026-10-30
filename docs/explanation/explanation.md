# Explanation

This page explains how the PLD schemas are put together and why. It is
background for users who want to understand the behaviour, and for maintainers
who change the schemas.

## From the mock-up to NOMAD

The schemas started from the PLD4Energy ELN mock-up (an HTML form) and the
users' feedback on it. The mock-up is a form, not a data model, so repeated
parts of the form became reusable sections:

| In the mock-up | In the schema |
| --- | --- |
| The gas checkboxes and flow fields, repeated in every step | One `BackgroundGas` section, repeated per gas in every step; the shared valve and the `UHV` / `Background gas` choice on the step |
| Laser fields, repeated in pre-ablation and deposition | One `LaserParameters` section (`laser`) |
| "Substrate stage start x/y/z/tilt/spin-position" | One `HeaterStagePosition` section with `x`, `y`, `z`, `tilt`, `spin` |
| Target stage fields | One `TargetStage` section |
| Laser details in the system details | `LaserCalibration` (`laser_details`) |
| Fields shown only for a choice (scan yes/no, polar/cartesian) | Optional sub-sections, added on save for the chosen option |
| "Number of targets/samples" counters | Repeating sub-sections: add as many as you need |
| In-situ techniques inside the deposition step | A separate `in_situ_techniques` section and a stand-alone entry type |

NOMAD forms cannot show or hide a field depending on another field. Conditional
fields are therefore optional sub-sections. The section for the chosen option is
added on save, so its fields appear without having to add it by hand.

## Entries and how they refer to each other

```
PLD Target (entry)                Sample (entry)
      ▲                             ▲        ▲
      │ target                      │ sample │ sample
      │                             │        │
SA-PLD / LA-PLD Logbook (entry)     │   PLD In-situ Techniques (entry)
├── samples[] ── sample ────────────┤   (new and external samples:
├── laser_details                   │    created on save)
├── targets[]  ── target ──► PLD Target
├── load_recipe ── recipe ──► earlier logbook of the same system
├── steps[]
│   ├── Pre-ablation step ── target ──► PLD Target
│   ├── Heating step
│   ├── Annealing step
│   ├── Pulsed laser deposition step ── target, samples[] ──► Sample
│   └── Cool-down step
└── in_situ_techniques
```

Targets, samples and logbooks are separate entries because each one has its
own life:

- A **target** is used in many runs. Storing it once means its material,
  manufacturer and purchase date are entered once, and every run that used it
  can be found from the target.
- A **sample** outlives the run that made it: it is measured later,
  post-processed, gets another film in a later run, or is used with a recipe.
  In-situ measurements and later runs refer to it.
- A **logbook** is one run.

NOMAD's reference picker searches for other entries; it cannot pick a section
inside the entry being edited. This is a second reason why targets and
samples are their own entries: steps can then pick them from a drop-down.

### Samples and substrates

A substrate is the template a film is grown on; after the deposition the
**sample** is the substrate with its films. Researchers start a run from the
samples they will make or process, so a logbook starts with a list of
`samples` (`SampleInRun`). Each is one of:

- a **new sample**: a substrate from the list, with the films planned for it;
- an **external sample**: prepared elsewhere, without a sample ID, so its
  substrate can also be described freely;
- an **existing sample**: made earlier in a PLD4Energy system and referenced, for
  an extra deposition, an annealing or only characterisation.

New and external samples get a sample ID `<system>_<yyyy-mm-dd>_<hh:mm>_S<nn>`
from the start of the run, numbered in the order of the list, and a name made
from the substrate and films (`SrTiO3_YSZ-20nm_SrRuO3-50nm`). The ID identifies
the sample and never changes once its entry exists; the name describes it. On
save the logbook creates a **Sample** entry for each of them (using
`create_archive` from `nomad-material-processing`) and links it. The file is
named after the sample ID. If a file with that name already exists, it is linked
rather than overwritten, so Sample entries are never replaced by accident. An
existing sample's entry is never changed by a logbook: it may be in another or
in a published upload. The films grown on it in this run are recorded in the
logbook.

The `Sample` section (`sample.py`) knows nothing about PLD: it records the
system it was made in as text. The same section and the `SampleRun` base of the
logbook can therefore be used by the sputter logbook and by later diagnostics,
so a sample made in one system can be processed and measured in another.

## SA-PLD and LA-PLD

Both logbooks share the `PLDLogbook` base: samples, system details, laser
details, targets, recipe, in-situ techniques and all step logic. They differ
only in:

| | SA-PLD | LA-PLD |
| --- | --- | --- |
| Substrate carriers | Omicron, 1" | Omicron, 1", 4" wafer, sample select |
| Particle reduction plate | – | `in use` / `not in use` |
| Samples of a deposition step | all samples loaded in the chamber | the chosen sample |
| Deposition step scan | substrate stage scan yes/no + scan width and speed | heater scan type: polar (default) or cartesian |

Each system has its own step classes (`SAPLDStep` and `LAPLDStep` and their
subclasses). When you add a step, NOMAD offers all sections that inherit from
the step type of the `steps` sub-section. Separate step classes mean an SA-PLD
logbook offers only SA-PLD steps. It also means the sputter deposition step,
which belongs to the separate sputter schema, is never offered in a PLD
logbook. The shared content of the steps (pre-ablation, heating, annealing,
deposition, cool-down) lives in common base classes, so it is defined only once.

## Generated (read-only) fields

Some fields have no input box: they are filled in by the plugin on save. This is
on purpose: these values are derived from other fields or from another entry,
and typing them by hand would let them disagree with their source.

| Field | Where | Why it is read-only | How to change it |
| --- | --- | --- | --- |
| PVD system | logbook | Fixed by the logbook type. A free choice would allow an "SA-PLD" logbook with LA-PLD carriers and steps. | Use the other logbook type. |
| Sample ID | samples in the logbook, Sample | Built as `<system>_<yyyy-mm-dd>_<hh:mm>_S<nn>`, so IDs always follow the same pattern. Kept once filled in, because labels and later runs refer to it. | Before the first save: change the system, start or order of the samples. |
| Sample UUID | samples in the logbook, Sample | Generated once and never changed, because it is printed on QR labels. Editing it would break the link between a label and its sample. | Not changeable. |
| Substrate material and size | Sample | Taken from the substrate. | Change the substrate. |
| Material, manufacturer, purchase date | targets in the logbook | Copied from the PLD Target entry, for checking your selection. | Correct the PLD Target entry. |
| Target number | pre-ablation and deposition steps | Copied from the target details, so the steps always show the number the target has in this run. | Change it in the target details. |
| Data status | in-situ techniques | Whether a data file has been added. | Add a data file. |
| Applied recipe | load recipe | A record of what was applied. | Apply a recipe. |
| Energy, intensity | LA-EDS | Calculated from / read from the spectrum. | Change E0 or the energy per channel. |

The sample **name** is generated too, but can be overwritten: it only describes
the sample.

!!! note
    The 1st window transmission is calculated but **not** read-only: you can
    override it, see [below](#laser-calibration).

## Laser calibration

The laser energy is measured before and after the chamber, so the beam passes
both windows between the two readings:

```
E_after = E_before × T1 × T2   →   T1 = E_after / (E_before × T2)
```

T2 (the 2nd window) is 92 % by default. T1 is calculated on every save unless
**transmission window 1 manual** is ticked and a value is entered; then the
typed value is kept. With a missing energy, or an energy before the chamber of
0, nothing is calculated.

The calibration and the targets are only needed when a step of the run uses the
laser. See [Laser and targets follow the process steps](#laser-and-targets-follow-the-process-steps).

!!! warning "Formula to be confirmed"
    The mock-up wrote the formula as `E_after / E_before × T₂`. Read literally
    (`(E_after / E_before) × T2`) that contradicts `E_after = E_before × T1 × T2`,
    so the schema uses `E_after / (E_before × T2)`. If the literal formula is
    meant, change `transmission_window_1()` in `laser.py`.

## Recipes

A recipe is not a separate entry type: any earlier logbook of the same system
can be used as one. Applying it copies the process steps into the current
logbook. Copying a snapshot, rather than linking to the recipe, means:

- the new logbook records exactly what was done in this run, even if the recipe
  logbook is edited later;
- the copied steps can be changed for this run without changing the recipe.

The `recipe` field keeps the link to where the steps came from.

The copy keeps references to targets, but replaces the samples of deposition
steps with the samples of this run (or the one chosen in the recipe loader).
This is how "do not copy the sample identity" is implemented. References to
entries in the recipe's upload are rewritten to absolute references, so they
still point to the right entry when the recipe comes from another upload.

The copy is triggered by a tick box (`apply_recipe`) that is unticked after the
copy. Saving again therefore does not copy again. See
[Reproduce a run with a recipe](../how_to/reuse_a_recipe.md) for the details.

## Units

Values are stored in SI units (Pa, J, m, K, s, ...) and shown in the units of
the lab (mbar, mJ, mm, nm, °C, min, ...). You type values in the shown unit in
the form. In archive files (YAML/JSON) values must be given in the SI unit.

Exceptions, stored as plain numbers:

- percentages (window transmissions, attenuator position, valve position,
  heater output), in %;
- gas flows are stored in cm³/min, which is the same number as sccm.

Ramp rates are in K/min, which is the same number as °C/min. Temperatures are
stored in K and shown in °C.

## In-situ techniques

In-situ techniques are their own section and not part of a deposition step,
because a sample can be measured outside a deposition run, e.g. during
post-processing of an older sample. They can be recorded in the logbook of the
run or in a stand-alone **PLD In-situ Techniques** entry. Both have optional
links to a sample and to a run.

For each technique the native file (which only the instrument software can
open) and the exported file (which other programs can read) are stored
separately where both exist. The data are often collected from several computers
after the run, so a technique can be saved without files: its `data_status` is
then `awaiting data`, with a warning on every save, until a file is added. The
run's metadata is safe in NOMAD in the meantime, and the missing data stays
visible.

The LA-EDS energy axis is not stored in the `.sp0` file and is rebuilt from E0
and the energy per channel. The `.sp0` reader is still to be written; the LA-EDS
spectrum supplier changes from RSX1000 to RaySpec RSX2000, so the reader is kept
separate and easy to replace.

## The PLD logbook dashboard

The dashboard lives in `src/differ_pld4e_schemas/dashboards/pld_logbook/`. It is part of this plugin, so the form and the schemas it writes are always released together.

### Why a dashboard

The NOMAD entry editor shows every field of a schema section and lets you save
at any time. It cannot hide a field depending on another field, and it cannot
refuse to save an incomplete entry. For the PLD logbooks this means users see
LA-PLD fields on SA-PLD runs, polar and cartesian scan fields at the same time,
and logbooks can be saved half-empty.

A dashboard plugin is a FastAPI app that NOMAD mounts under
`<NOMAD URL>/dashboards/<id>/`, so it runs on the same origin as NOMAD and can
use the NOMAD API with the user's session. The PLD logbook dashboard uses that
to offer its own form with conditional fields and a completeness check, and
then writes normal NOMAD entries of the PLD4Energy schemas.

### How it fits together

```
browser (static/app.js)                     dashboard app (FastAPI)
  form, live checks  ── GET  api/spec ──►     spec.py   form definition
                     ── POST api/archive ─►   rules.py  validation (again)
                     ◄─ archive files ────    convert.py form ⇄ archive (SI units)
                     ── POST api/draft-name   (where a draft is kept)
                     ── POST api/form-from-archive (open logbook / recipe)

browser ──► NOMAD API (with the user's session)
  /users/me, /uploads, /entries/query, /entries/archive/query,
  PUT/GET/DELETE /uploads/<id>/raw/...  (in-situ files, drafts, archives)
  GET /uploads/<id>/rawdir/pld_drafts   (list drafts)
```

- **`spec.py`** is the single definition of the form: sections, fields, units,
  choices, which fields are required and when a field is shown (`visible_if`).
  The browser renders the form from it and the server validates against it.
- **`rules.py`** computes values (1st window transmission, sample IDs and
  names), how much of a section the process steps need, and validates a form.
  `static/app.js` contains the same rules so problems show while typing; the
  server always validates again before it builds anything.
- **`convert.py`** turns a complete form into archive files and reads saved
  logbooks back into a form.

The parts that do not depend on PLD are in `dashboards/common/`, so a sputter
logbook dashboard can reuse them:

- `fields.py` builds field definitions;
- `values.py` evaluates conditions and reads form values;
- `archive.py` maps form values to archive quantities, converting from the unit
  of the form field to the unit of the schema quantity with pint;
- `samples.py` is the *Samples* section: its fields, sample IDs and names, and
  the Sample files.

### Laser and targets follow the process steps

Each step type declares whether it needs the laser: `required` (pre-ablation,
deposition), `optional` or `none` (heating, annealing, cool-down). A section with
`requirement: {'from_steps': 'laser'}`, the laser details and the targets, is
needed as much as the step that needs it most:

| Steps of the run | Laser details and targets |
| --- | --- |
| at least one step needs the laser | required |
| a step may use the laser | optional: saved if filled in |
| no step uses the laser | not needed: not checked and not saved |

A step type with an optional laser gets a *Laser used* switch in front of its
laser fields; once switched on, that step counts as needing the laser. No PLD
step uses this yet; it is there for step types to come.

### Completeness

A field is required when it is visible and marked `required`. Hidden fields are
never required, so choosing *Cartesian scan* makes the cartesian fields required
and the polar fields irrelevant. Lists have a minimum number of items and unique
values (targets, target numbers, sample IDs, existing samples). In-situ data
files are not required: a technique without files is saved as awaiting data.

The save button stays disabled while anything is missing, and `api/archive`
refuses to build archive files for an incomplete form, so incomplete logbooks
cannot be written through the dashboard.

### Drafts

Users must log every step of a run, also external users of the facility, but a
run is often filled in on several computers. Saving incomplete logbooks would
let half-logged runs end up in NOMAD as data. Instead, an unfinished run can be
saved as a **draft**: the form state as a plain JSON file,
`pld_drafts/<system>_<date>_<hhmm>[_<run name>].draft.json`, in the upload.

- No NOMAD parser reads `.draft.json` files, so a draft is never an entry: it is
  not searchable, creates no Sample entries and does not count as logged.
- Any computer can continue it (the start page lists the drafts in the user's
  unpublished uploads). In-situ files picked for a draft are uploaded with it.
- Before a draft is overwritten, it is read again: if another computer saved it
  in the meantime, the user chooses which version to keep.
- The final save creates the entries and deletes the draft.

A draft only needs the system, date and start time, which name the file. The
form is also kept in the browser's local storage, as a safeguard on the same
computer.

### Saving

1. The form is validated by the server, which also returns the file name of the
   logbook (`<system>_<date>_<hhmm>[_<run name>].archive.json`).
2. In-situ files are uploaded to `pld_files/<logbook file name>/`.
3. One Sample archive is written per new or external sample, named after its
   sample ID, and the logbook archive refers to it by file name. A Sample that
   this logbook created before is written again (overwritten), so corrections
   made in the dashboard reach it; existing samples of other runs are never
   written.
4. The logbook is written. A new logbook never overwrites an existing file; an
   opened logbook is overwritten.
5. The draft of the run, if any, is deleted.

Each file is written with `wait_for_processing=true`, so NOMAD's processing
errors and warnings are shown in the log.

The start of the run is saved with the browser's UTC offset. NOMAD stores it in
UTC, so the dashboard shows it in local time again when a logbook is opened. The
sample IDs use the local time and are kept once their entries exist.

### Conditional fields

Conditions are small JSON objects, evaluated in the browser and on the server:

```python
{'key': 'heater_scan_type', 'equals': 'Polar scan'}  # same step
{'key': '/run/system', 'equals': 'LA-PLD'}  # anywhere in the form
{'key': 'origin', 'in': ['New sample', 'External sample']}
{'key': '/steps', 'has_type': ['deposition']}  # a step of a type exists
{'all': [...]} / {'any': [...]}  # combinations
```

Choices can also depend on another field (`options_by`), e.g. the substrate
carriers depend on the PVD system.
