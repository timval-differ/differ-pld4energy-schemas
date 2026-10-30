# Use the PLD logbooks

Short guides for the everyday tasks. For a complete walk-through of a run, see
the [tutorial](../tutorial/tutorial.md). For every field and unit, see the
[reference](../reference/references.md).

!!! note "Save to update"
    Calculated and copied values (sample IDs and names, 1st window transmission, target
    numbers, copied recipe steps, ...) are updated when the entry is **saved**,
    and the checks run at the same time. Messages appear after saving.

## Manage the target database

Every physical target is one **PLD Target** entry.

- **Add a target:** create a PLD Target entry with material, manufacturer and
  purchase date (optionally diameter, thickness, purity).
- **Naming:** the entry is named after the **name** field, or after the material
  if the name is empty. Do not put the target number in the name: target
  positions change, and the number is entered per run in the logbook.
- **Two targets of the same material:** give them different names, e.g.
  `Fe2O3 (Praxair 2024)` and `Fe2O3 (Pi-Kem 2025)`, so you can tell them apart
  in the drop-down.

## Manage the substrate database

Every kind of substrate in use is one **Substrate type** entry, e.g.
`SrTiO3 10x10 mm`, `Si 1" with flat`, `Si 1" without flat`, `glass` or `FTO`.
Samples refer to it.

- **Add a substrate:** create a Substrate type entry with the **material** and
  **size** (optionally supplier and description). The material is used in the
  sample names, so write it as it should appear there, e.g. `SrTiO3`.
- **Naming:** the entry is named after the **name** field, or after the
  material and size if the name is empty.

## Start a logbook

Create an **SA-PLD Logbook** or **LA-PLD Logbook**. Pick the logbook of the
system you ran on: it decides which carriers, step types and scan options are
offered, and the **PVD system** field is set by it.

Fill in the operator name and email, the start of the run (**datetime**,
defaults to the first save) and optionally a name. Then list the
[samples](#list-the-samples-of-a-run), and fill in the system details: base
pressure of the main chamber (mbar) and substrate carrier. For LA-PLD, also set
**particle reduction plate**.

## Record the laser calibration

The laser details and the targets are only needed for runs with a step that
uses the laser (pre-ablation or deposition). The
[dashboard](use_the_dashboard.md) does not ask for them, and does not save them,
for a run with only annealing or characterisation.

Open **laser details** and enter the energy before and after the chamber (mJ).
Transmission of the 2nd window is pre-filled with 92 %.

On save, the 1st window transmission is calculated as
`T1 = E_after / (E_before × T2)`:

| You did | Result on save |
| --- | --- |
| Entered both energies | T1 is calculated (and recalculated on every save). |
| Typed your own T1, **manual** not ticked | Your value is replaced by the calculated one. |
| Typed your own T1 and ticked **manual** | Your value is kept. |
| Ticked **manual** but left T1 empty | T1 is calculated. |
| Energy before chamber is 0 or an energy is missing | T1 is not calculated (a warning is given for 0). |

## Select the targets of a run

Add one **targets** entry per target in the system: pick the PLD Target and
enter its **target number**, its position in the system for this run (1 to 5).
A number outside 1 to 5 gives a warning. Material, manufacturer and purchase
date are copied in on save so you can check your choice.

Checks: selecting the same target twice is an **error**; using a target number
twice is a **warning**.

## List the samples of a run

A substrate is the template a film is grown on; a sample is the substrate with
its films. Add one **samples** entry per sample the run makes or processes:

| Origin | When | Fill in |
| --- | --- | --- |
| New sample | most runs | substrate (from the substrate database), films |
| External sample | prepared elsewhere, no sample ID yet | substrate, or no substrate and substrate details; the films it came with in **prior layers**; films; what you know in comments |
| Existing sample | made earlier in a PLD4Energy system, e.g. for an extra deposition, annealing or characterisation | the Sample entry in **sample**; films grown in this run |

The films grown in this run are **layers** entries, each with the **target** it
is grown from and its thickness (nm); its **material** is taken from the target.
The [dashboard](use_the_dashboard.md) fills them in from the deposition steps
(one film per step, with the step's target and film thickness); in the entry
editor you add them yourself. Films an external sample already had when it came
in are **prior layers** (material and, if known, thickness); they come first in
its name and in its Sample entry. The substrate's material and size are copied
in as well. On save, for new and external samples:

- **sample ID** becomes `<system>_<yyyy-mm-dd>_<hh:mm>_S<nn>`, from the logbook's
  start; the new and external samples of the run are numbered S01, S02, ... in
  order. A sample ID that is already filled in is kept.
- **name** becomes `Substrate_Film-<t>nm_Film-<t>nm`, e.g.
  `SrTiO3_YSZ-20nm_SrRuO3-50nm`, unless you entered one. The name describes the
  sample; the ID identifies it.
- **sample UUID** is generated once and never changes.
- a **Sample** entry is created in the same upload (file
  `<sample ID>.archive.json`) and linked in **sample**.

For an existing sample, its ID and name are copied from its entry; the entry
itself is not changed. Two samples with the same ID give a warning.

!!! warning "The sample entry is created once"
    After the Sample entry exists, changes to the sample in the logbook are
    **not** copied to it by the entry editor. Correct the Sample entry itself.
    (The [dashboard](use_the_dashboard.md) does update the Sample entries it
    created when you save the logbook again.)

## Add process steps

Add steps under **steps** in the order they were done. Only the steps of the
logbook's own system are offered: pre-ablation, heating, annealing, pulsed laser
deposition and cool-down. There is deliberately no sputter step in the PLD
logbooks. Add a step type as often as you need; for a multilayer just add
another deposition step. A run without deposition is fine.

### Background gases (every step)

Set **atmosphere** to `UHV` when no gas was let in: then only the step's
**pressure** is recorded. Otherwise leave it at `Background gas` and add one
**background gases** entry per gas that was on:

| Field | Meaning |
| --- | --- |
| gas | `Ar`, `O2` or `N2` |
| set flow | flow set on the controller (sccm) |
| read-out flow | flow measured / read out (sccm) |

All gases share one valve, so the valve is recorded once per step:

| Field | Meaning |
| --- | --- |
| valve position | valve position on the controller (%) |
| valve position fixed | ticked if the valve was kept at a fixed position |

Gases listed in a UHV step give a warning.

### Heating and annealing

Heating steps and annealing steps record the **heater output** (%) once the
temperature setpoint is reached. An annealing step also has the **dwell time**
at the setpoint.

### Target of a pre-ablation or deposition step

Pick the target in **target**. The **target number** is taken from the target
details on save, so the step always shows the current number. If only one target
is selected in the logbook, empty step targets are filled in automatically. A
step target that is not selected in the target details gives a warning.

### Laser settings

The **laser** sub-section of pre-ablation and deposition steps holds laser mode,
laser voltage (kV), magnification, mask size, **spot size** (mm²), fluence
(J/cm²), energy (mJ), attenuator position (%), frequency (Hz) and number of
pulses.

### Heater stage

Deposition steps have a **heater stage position** with x, y, z (mm), tilt and
spin (degrees), the **film thickness** (nm) of the film they grow, and list the
**samples** deposited on: in the SA-PLD all samples loaded in the chamber, in
the LA-PLD the sample of the step.

- **SA-PLD:** tick **substrate stage scan** if the stage scanned. On save a
  **substrate scan** sub-section is added for the scan width (mm) and scan speed
  (mm/s) in x and y. Scan values while the box is unticked give a warning.
- **LA-PLD:** choose **heater scan type**: `Polar scan` (default) or
  `Cartesian scan`. On save the matching sub-section is added:

    | Polar scan | Unit |
    | --- | --- |
    | radius start | mm |
    | radius stop | mm |
    | pulse spacing | mm |
    | max laser frequency | Hz |
    | number of scans | – |

    Values in the scan type that is not selected are ignored, with a warning.

### Target stage

Pre-ablation and deposition steps have a **target stage** sub-section: start
x/y/z position, x/y offset, scan width in x and y (mm) and scan speed in x and
y (mm/s).

## Reproduce a run

See [Reproduce a run with a recipe](reuse_a_recipe.md).

## Record in-situ measurements

In-situ techniques are a separate part of the logbook (**in situ techniques**),
not part of a step. For measurements that do not belong to a new run, e.g. an
older sample that is post-processed, create a stand-alone **PLD In-situ
Techniques** entry. Its **sample** (a Sample) and **process** (a logbook)
fields are optional.

Data files are often collected from other computers after the run. A technique
can be saved without them: its **data status** is then `awaiting data` and a
warning reminds you, until a file is added (`complete`).

Add one sub-section per technique (more than one per technique is allowed, e.g.
one RHEED entry per capture):

| Technique | Software | Fields |
| --- | --- | --- |
| RHEED | KSA 400 | pattern capture: native `.img` and exported `.png`; ROI intensity map: native `.kdt` and exported `.txt` |
| MIC | EZ-Curve | native `.ezc` and exported `.csv` |
| LA-EDS | RSX1000 (later RaySpec RSX2000) | `.sp0` file, energy offset E0 (eV), energy per channel (eV), number of channels |
| SE, OES, SHG | – | one data file each |

Native files can only be reopened in the instrument software. Upload them
anyway: they are the raw data. The exported files can be opened elsewhere.

### LA-EDS spectrum

The `.sp0` file has no energy axis; it is rebuilt as
`E = E0 + channel number × energy per channel` (channels counted from 0) and
plotted as intensity versus energy.

!!! note "Not yet automatic"
    The `.sp0` file is not read yet: the location of E0 in the file still has to
    be confirmed with an example file. Until then the spectrum (intensity per
    channel) can only be added via an archive file, together with E0 and the
    energy per channel.

## Write logbooks as archive files

Instead of using the form, you can upload YAML or JSON archive files; see
`tests/data/example_sa_pld.archive.yaml` and
`tests/data/example_la_pld.archive.yaml`.

- Use `m_def: differ_pld4e_schemas.schema_packages.schema_package.SAPLDLogbook`
  (or `LAPLDLogbook`, `PLDTarget`, `Sample`, `InSituTechniquesEntry`).
  Steps need their own `m_def`, e.g. `...schema_package.SAPLDDepositionStep`.
- **Numbers are in SI units** in archive files, whatever the form shows: Pa
  (not mbar), J (not mJ), m (not mm), K (not °C), m² for spot size, J/m² for
  fluence. For example 1e-8 mbar is `1.0e-6`, 500 mJ is `0.5` and 700 °C is `973.15`.
- Reference an entry in the same upload by file name:
  `'../upload/archive/mainfile/<file name>#data'`.

## Messages after saving

| Message | Level | What to do |
| --- | --- | --- |
| Target ... is selected more than once. | error | Remove the duplicate target. |
| Target number ... is used twice. | warning | Correct the target numbers. |
| Sample ... is listed twice. | warning | Two samples have the same sample ID; correct one. |
| Select the existing sample. | warning | Pick the Sample entry of an existing sample. |
| Step ... uses a target that is not selected in the target details. | warning | Add the target to the target details or change the step. |
| Step ... is in UHV but lists background gases. | warning | Set the atmosphere to background gas or remove the gases. |
| RHEED (or another technique): no data file has been added yet. | warning | Add the data files when you have them. |
| Laser energy before chamber is 0, cannot compute T1. | warning | Correct the energy. |
| Scan parameters are given but substrate stage scan is off. | warning | Tick the scan or remove the scan values (SA-PLD). |
| Cartesian/Polar scan parameters are ignored for a ... scan. | warning | Check the heater scan type (LA-PLD). |
| Select a recipe before applying it. | error | Pick a recipe in load recipe. |
| The recipe is from ..., not from .... | error | Use a recipe of the same system. |
| LA-EDS number of channels does not match the intensity. | warning | Check the number of channels. |
