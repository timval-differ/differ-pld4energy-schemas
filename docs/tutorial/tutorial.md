# Tutorial: your first SA-PLD run

This tutorial walks through recording one complete SA-PLD run in the NOMAD entry
editor: SrTiO3 deposited on a Si substrate. You will:

1. add the target to the target database,
2. create the logbook and list the samples of the run,
3. fill in the system details,
4. add the process steps,
5. select the targets and fill in the laser details,
6. attach in-situ data.

The LA-PLD logbook works the same way; the differences are listed at the end.
The [PLD logbook dashboard](../how_to/use_the_dashboard.md) guides you through
the same steps in a form and only shows the fields that apply.

!!! note "Saving"
    Many fields are filled in or checked when you **save** the entry: the
    sample IDs and names, the 1st window transmission, the target number in
    each step, and so on. If a value you expect is missing, save first.

## 1. Add the target to the target database

Targets are stored once, as their own **PLD Target** entries, and reused by
every run.

1. In your upload, create a new entry of type **PLD Target**.
2. Fill in **material** (`SrTiO3`), **manufacturer** (`Pi-Kem`) and
   **purchase date**. Optionally add diameter, thickness and purity.
3. Save. The entry is named after the material (`SrTiO3`). You can set a
   different **name** if you have two targets of the same material, e.g.
   `SrTiO3 (Pi-Kem 2024)`.

!!! tip
    The target number is **not** part of the target entry. Targets are moved in
    and out of the system, so the number is entered per run in the logbook.
    The films of a sample are linked to the target they are grown from, and
    take their material from it.

If the target already exists, skip this step.

Substrates work the same way: every kind of substrate is one **Substrate type**
entry with its **material** (`Si`) and **size** (`1" with flat`). Create one
if the substrate you use is not there yet.

## 2. Create the logbook and list the samples

1. Create a new entry of type **SA-PLD Logbook**.
2. Fill in the run:
    - **operator name** and **operator email**: who does the run;
    - **datetime**: the start of the run. If you leave it empty it is set to
      the moment you first save;
    - **name**: optional, a short name for the run, e.g. `STO on Si`.

**PVD system** is already set to `SA-PLD` and cannot be changed: it is fixed by
the logbook type (see [Explanation](../explanation/explanation.md#generated-read-only-fields)).

### Samples

A run starts with the samples it makes or processes. A substrate is the
template a film is grown on; the sample is the substrate with its films. Add one
**samples** sub-section per sample:

- **origin**: `New sample` (most runs), `External sample` (prepared elsewhere,
  without a sample ID) or `Existing sample` (made earlier in a PLD4Energy
  system, e.g. for an extra deposition or only annealing);
- for a new or external sample, the **substrate** from the substrate database
  (e.g. `Si 1" with flat`); an external sample on a substrate that is not in
  the database gets **substrate details** instead, and the films an external
  sample came with go in **prior layers**;
- for an existing sample, the **sample** entry itself;
- **layers**: one per film grown in this run, with its **target** (e.g.
  `SrTiO3`) and **thickness** (nm), e.g. 20 nm. The film material is taken from
  the target. (The dashboard fills these in from the deposition steps.);
- **comments**.

Save. For each new and external sample the plugin then:

- fills in the **sample ID** as `SA-PLD_<yyyy-mm-dd>_<hh:mm>_S<nn>`, e.g.
  `SA-PLD_2026-10-22_09:00_S01`, numbering the new and external samples of the
  run in order;
- fills in the **name** from the substrate and films, e.g. `Si_SrTiO3-20nm`;
- generates a **sample UUID** (use it for a QR label);
- creates a **Sample** entry in the same upload and links it in **sample**.

That Sample entry is the sample's identity from now on: deposition steps,
recipes and later in-situ measurements refer to it. An existing sample is only
linked; its entry is not changed.

!!! tip
    The sample ID uses the time of the logbook's **datetime** as NOMAD stores
    it, in UTC. The dashboard uses your local time instead.

## 3. Fill in the system details

- **substrate carrier**: `Omicron carrier` or `1" carrier`;
- **base pressure** of the main chamber (mbar);
- **description** for comments.

## 4. Add the process steps

Add sub-sections to **steps** in the order you ran them. The logbook only offers
SA-PLD steps: **Pre-ablation step**, **Heating step**, **Annealing step**,
**Pulsed laser deposition step** and **Cool-down step**. You can add each type
as often as you need, e.g. deposition, heating, deposition for a multilayer. A
run without deposition, e.g. only annealing, is fine.

Every step has:

- **pressure** (mbar) during the step;
- **atmosphere**: `UHV` (only the pressure is recorded) or `Background gas`;
- **background gases**: one entry per gas, with the gas (`Ar`, `O2` or `N2`),
  the **set flow** and **read-out flow** (sccm);
- **valve position** (%) and whether it was **fixed**: one valve for all gases;
- **description** for comments.

### Pre-ablation step

- **target**: one of the targets of the run (see step 5). If only one target is
  selected, it is filled in on save. The **target number** is copied from the
  target details.
- **substrate temperature** (°C);
- **target stage**: start x/y/z position, x/y offset, scan width in x and y
  (mm) and scan speed in x and y (mm/s);
- **laser**: laser mode, laser voltage (kV), magnification, mask size,
  **spot size** (mm²), fluence (J/cm²), energy (mJ), attenuator position (%),
  frequency (Hz) and number of pulses.

### Heating, annealing and cool-down steps

- Heating and cool-down: **ramp rate** (K/min, which is the same number as
  °C/min) and **temperature setpoint** (°C).
- Heating and annealing: **heater output** (%) once the setpoint is reached.
- Annealing: **temperature setpoint** and **dwell time** at that temperature.

### Pulsed laser deposition step

Everything from the pre-ablation step, plus:

- **film thickness** (nm) of the film this step grows;
- **samples**: the samples deposited on. In the SA-PLD that is every sample
  loaded in the chamber;
- **heater stage position**: x, y, z (mm), tilt and spin (degrees);
- **substrate stage scan**: tick it if the substrate stage scanned. On save a
  **substrate scan** sub-section is added for the scan width (mm) and scan speed
  (mm/s) in x and y.

## 5. Select the targets and fill in the laser details

These are only needed when a step uses the laser (pre-ablation and deposition).
For a run with only annealing, skip this step.

### Targets

Add one **targets** sub-section per target loaded in the system:

- **target**: pick `SrTiO3` from the target database;
- **target number**: the position of the target in the system today, 1 to 5.

Save. Material, manufacturer and purchase date are copied from the target entry
so you can check you picked the right one. Selecting the same target twice is
reported as an error; using the same target number twice gives a warning.
Check the messages after saving: a warning tells you, for example, that a step
uses a target that is not in the target details.

### Laser details

Do the laser calibration as described in the section description: attenuator
100% open, 1 Hz, HV NGR mode with HV = 22 kV, 500 mJ, mask 5x18 mm. Then open
**laser details** and enter:

- **energy before chamber** and **energy after chamber** (mJ);
- **transmission window 2**: pre-filled with 92 %, change it if needed.

Save. **Transmission window 1** is calculated for you as
`T1 = E_after / (E_before × T2)`. To enter your own value instead, tick
**transmission window 1 manual**, type the value and save.

## 6. Attach in-situ data

Open **in situ techniques** in the logbook and add a sub-section for each
technique you used: RHEED, MIC, SE, LA-EDS, OES or SHG. Upload the files into
the matching fields, e.g. for RHEED the native `.img` capture and the exported
`.png`. A technique without files is shown as **awaiting data**, so you can add
data collected on other computers later. See
[Use the PLD logbooks](../how_to/use_this_plugin.md#record-in-situ-measurements)
for the details per technique.

## Differences for an LA-PLD run

Use an **LA-PLD Logbook** instead. Everything above applies, plus:

- the **substrate carrier** also offers `4" wafer carrier` and `Sample select carrier`;
- **particle reduction plate**: `in use` or `not in use`;
- a deposition step is linked to the sample it deposits on;
- the deposition step has a **heater scan type**, `Polar scan` (default) or
  `Cartesian scan`, instead of the substrate stage scan. On save the matching
  sub-section is added:
    - **polar scan**: radius start, radius stop, pulse spacing (mm), max laser
      frequency (Hz) and number of scans;
    - **cartesian scan**: x/y offset, scan rate and rotation rate.

## Next steps

- Repeat this run on new samples: [Reproduce a run with a recipe](../how_to/reuse_a_recipe.md).
- Look at complete example entries: `tests/data/example_sa_pld.archive.yaml` and
  `tests/data/example_la_pld.archive.yaml` in the plugin repository.
