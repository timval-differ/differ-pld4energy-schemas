# Tutorial: your first SA-PLD run

This tutorial walks through recording one complete SA-PLD run: SrTiO3 deposited
on a Si substrate. You will:

1. add the target to the target database,
2. create the logbook and fill in the system and laser details,
3. select the target and create the substrate,
4. add the process steps,
5. attach in-situ data.

The LA-PLD logbook works the same way; the differences are listed at the end.

!!! note "Saving"
    Many fields are filled in or checked when you **save** the entry: the
    sample ID, the 1st window transmission, the target number in each step,
    and so on. If a value you expect is missing, save first.

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

If the target already exists, skip this step.

## 2. Create the logbook

1. Create a new entry of type **SA-PLD Logbook**.
2. Fill in the run details:
    - **name**: a short name for the run, e.g. `STO on Si`;
    - **datetime**: the run date. If you leave it empty it is set to the moment
      you first save;
    - **base pressure** (mbar);
    - **substrate carrier**: `Omicron carrier` or `1" carrier`.

**PVD system** is already set to `SA-PLD` and cannot be changed: it is fixed by
the logbook type (see [Explanation](../explanation/explanation.md#generated-read-only-fields)).

### Laser details

Do the laser calibration as described in the section description: attenuator
100% open, 1 Hz, HV NGR mode with HV = 22 kV, 500 mJ, mask 5x18 mm. Then open
**laser details** and enter:

- **energy before chamber** and **energy after chamber** (mJ);
- **transmission window 2**: pre-filled with 92 %, change it if needed.

Save. **Transmission window 1** is calculated for you as
`T1 = E_after / (E_before × T2)`. To enter your own value instead, tick
**transmission window 1 manual**, type the value and save.

## 3. Select the target and create the substrate

### Targets

Add one **targets** sub-section per target loaded in the system:

- **target**: pick `SrTiO3` from the target database;
- **target number**: the position number of the target in the system today.

Save. Material, manufacturer and purchase date are copied from the target entry
so you can check you picked the right one. Selecting the same target twice is
reported as an error; using the same target number twice gives a warning.

### Substrates

Add one **substrates** sub-section per substrate:

- **sample name**: e.g. `Si_STO-20nm` (suggested format
  `Substrate_ThinFilm-thickness_next_layer`);
- **run number** and **sample number**;
- **size**, **substrate material** and **comments**.

Save. The plugin then:

- fills in **sample user ID** as `SA-PLD_<date>_<run>_<sample number>`, e.g.
  `SA-PLD_2026-10-22_1_1`;
- generates a **sample UUID** (use it for a QR label);
- creates a **PLD Substrate** entry for the substrate in the same upload and
  links it in **substrate**.

That PLD Substrate entry is the sample's identity from now on: deposition steps,
recipes and later in-situ measurements refer to it.

## 4. Add the process steps

Add sub-sections to **steps** in the order you ran them. The logbook only offers
SA-PLD steps: **Pre-ablation step**, **Heating step**, **Pulsed laser deposition
step** and **Cool-down step**. You can add each type as often as you need, e.g.
deposition, heating, deposition for a multilayer.

Every step has:

- **pressure** (mbar) during the step;
- **background gases**: add one entry per gas, with the gas (`Ar`, `O2` or
  `N2`), the **set flow** and **read-out flow** (sccm), the **valve position**
  and whether the valve position was **fixed**;
- **description** for comments.

### Pre-ablation step

- **target**: one of the targets from step 3. If only one target is selected,
  it is filled in on save. The **target number** is copied from the target
  details.
- **substrate temperature** (°C);
- **target stage**: start x/y position, x/y offset, scan area (mm);
- **laser**: laser mode, laser voltage (kV), magnification, mask size,
  **spot size** (mm²), fluence (J/cm²), energy (mJ), attenuator position (%),
  frequency (Hz) and number of pulses.

### Heating and cool-down steps

**Ramp rate** (K/min, which is the same number as °C/min) and **temperature
setpoint** (°C), plus pressure and gases.

### Pulsed laser deposition step

Everything from the pre-ablation step, plus:

- **substrate**: the PLD Substrate created in step 3;
- **heater stage position**: x, y, z (mm), tilt and spin (degrees);
- **substrate stage scan**: tick it if the substrate stage scanned. On save a
  **cartesian scan** sub-section is added for the x/y offset (mm), scan rate
  (mm/s) and rotation rate (rpm).

Save. Check the messages after saving: a warning tells you, for example, that a
step uses a target that is not in the target details.

## 5. Attach in-situ data

Open **in situ techniques** in the logbook and add a sub-section for each
technique you used: RHEED, MIC, SE, LA-EDS, OES or SHG. Upload the files into
the matching fields, e.g. for RHEED the native `.img` capture and the exported
`.png`. See [Use the PLD logbooks](../how_to/use_this_plugin.md#record-in-situ-measurements)
for the details per technique.

## Differences for an LA-PLD run

Use an **LA-PLD Logbook** instead. Everything above applies, plus:

- the **substrate carrier** also offers `4" wafer carrier` and `Sample select carrier`;
- **particle reduction plate**: `in use` or `not in use`;
- the deposition step has a **heater scan type**, `Polar scan` (default) or
  `Cartesian scan`. On save the matching sub-section is added:
    - **polar scan**: radius start, radius stop, pulse spacing (mm), max laser
      frequency (Hz) and number of scans;
    - **cartesian scan**: x/y offset, scan rate and rotation rate.

## Next steps

- Repeat this run on a new substrate: [Reproduce a run with a recipe](../how_to/reuse_a_recipe.md).
- Look at complete example entries: `tests/data/example_sa_pld.archive.yaml` and
  `tests/data/example_la_pld.archive.yaml` in the plugin repository.
