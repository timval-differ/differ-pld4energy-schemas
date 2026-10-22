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
| The gas checkboxes and flow fields, repeated in every step | One `BackgroundGas` section, repeated per gas in every step |
| Laser fields, repeated in pre-ablation and deposition | One `LaserParameters` section (`laser`) |
| "Substrate stage start x/y/z/tilt/spin-position" | One `HeaterStagePosition` section with `x`, `y`, `z`, `tilt`, `spin` |
| Target stage fields | One `TargetStage` section |
| Laser details in the system details | `LaserCalibration` (`laser_details`) |
| Fields shown only for a choice (scan yes/no, polar/cartesian) | Optional sub-sections, added on save for the chosen option |
| "Number of targets/substrates" counters | Repeating sub-sections: add as many as you need |
| In-situ techniques inside the deposition step | A separate `in_situ_techniques` section and a stand-alone entry type |

NOMAD forms cannot show or hide a field depending on another field. Conditional
fields are therefore optional sub-sections. The section for the chosen option is
added on save, so its fields appear without having to add it by hand.

## Entries and how they refer to each other

```
PLD Target (entry)            PLD Substrate (entry)
      ▲                           ▲          ▲
      │ target                    │ substrate│ sample
      │                           │          │
SA-PLD / LA-PLD Logbook (entry)   │    PLD In-situ Techniques (entry)
├── laser_details                 │
├── targets[]  ── target ─────────┼──► PLD Target
├── substrates[] ── substrate ────┘   (created on save)
├── load_recipe ── recipe ──► earlier logbook of the same system
├── steps[]
│   ├── Pre-ablation step ── target ──► PLD Target
│   ├── Heating step
│   ├── Pulsed laser deposition step ── target, substrate
│   └── Cool-down step
└── in_situ_techniques
```

Targets, substrates and logbooks are separate entries because each one has its
own life:

- A **target** is used in many runs. Storing it once means its material,
  manufacturer and purchase date are entered once, and every run that used it
  can be found from the target.
- A **substrate** (sample) outlives the run that made it: it is measured later,
  post-processed, or used as a recipe target. In-situ measurements and later
  runs refer to it.
- A **logbook** is one run.

NOMAD's reference picker searches for other entries; it cannot pick a section
inside the entry being edited. This is a second reason why targets and
substrates are their own entries: steps can then pick them from a drop-down.

### Why substrates are created by the logbook

The mock-up creates substrates inside the run form, and the sample user ID
needs the run's system and date. So you fill in the substrate in the logbook,
and on save the logbook creates a **PLD Substrate** entry from it (using
`create_archive` from `nomad-material-processing`) and links it. The file is
named after the sample user ID. If a file with that name already exists, it is
linked rather than overwritten, so substrate entries are never replaced by
accident.

## SA-PLD and LA-PLD

Both logbooks share the `PLDLogbook` base: system details, laser details,
targets, substrates, recipe, in-situ techniques and all step logic. They differ
only in:

| | SA-PLD | LA-PLD |
| --- | --- | --- |
| Substrate carriers | Omicron, 1" | Omicron, 1", 4" wafer, sample select |
| Particle reduction plate | – | `in use` / `not in use` |
| Deposition step scan | substrate stage scan yes/no + cartesian scan | heater scan type: polar (default) or cartesian |

Each system has its own step classes (`SAPLDStep` and `LAPLDStep` and their
subclasses). When you add a step, NOMAD offers all sections that inherit from
the step type of the `steps` sub-section. Separate step classes mean an SA-PLD
logbook offers only SA-PLD steps. It also means the sputter deposition step,
which belongs to the separate sputter schema, is never offered in a PLD
logbook. The shared content of the steps (pre-ablation, heating, deposition,
cool-down) lives in common base classes, so it is defined only once.

## Generated (read-only) fields

Some fields have no input box: they are filled in by the plugin on save. This is
on purpose: these values are derived from other fields or from another entry,
and typing them by hand would let them disagree with their source.

| Field | Where | Why it is read-only | How to change it |
| --- | --- | --- | --- |
| PVD system | logbook | Fixed by the logbook type. A free choice would allow an "SA-PLD" logbook with LA-PLD carriers and steps. | Use the other logbook type. |
| Sample user ID | substrates in the logbook, PLD Substrate | Built as `<system>_<date>_<run>_<sample number>`, so IDs always follow the same pattern and match the data they are made of. | Change the system, date, run number or sample number. |
| Sample UUID | substrates in the logbook, PLD Substrate | Generated once and never changed, because it is printed on QR labels. Editing it would break the link between a label and its sample. | Not changeable. |
| Material, manufacturer, purchase date | targets in the logbook | Copied from the PLD Target entry, for checking your selection. | Correct the PLD Target entry. |
| Target number | pre-ablation and deposition steps | Copied from the target details, so the steps always show the number the target has in this run. | Change it in the target details. |
| Applied recipe | load recipe | A record of what was applied. | Apply a recipe. |
| Energy, intensity | LA-EDS | Calculated from / read from the spectrum. | Change E0 or the energy per channel. |

In the **PLD Substrate** entry itself, PVD system, run number and sample number
are editable. A substrate entry can also be created by hand, without a
logbook, and needs these fields for its sample user ID.

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

The copy keeps references to targets, but replaces the substrate of deposition
steps with the chosen substrate. This is how "do not copy the substrate
identity" is implemented. References to entries in the recipe's upload are
rewritten to absolute references, so they still point to the right entry when
the recipe comes from another upload.

The copy is triggered by a tick box (`apply_recipe`) that is unticked after the
copy. Saving again therefore does not copy again. See
[Reproduce a run with a recipe](../how_to/reuse_a_recipe.md) for the details.

## Units

Values are stored in SI units (Pa, J, m, K, ...) and shown in the units of the
lab (mbar, mJ, mm, °C, ...). You type values in the shown unit in the form. In
archive files (YAML/JSON) values must be given in the SI unit.

Exceptions, stored as plain numbers:

- percentages (window transmissions, attenuator position, valve position), in %;
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
separately where both exist. The LA-EDS energy axis is not stored in the
`.sp0` file and is rebuilt from E0 and the energy per channel. The `.sp0` reader
is still to be written; the LA-EDS spectrum supplier changes from RSX1000 to
RaySpec RSX2000, so the reader is kept separate and easy to replace.
