# Use the logbook dashboards

The plugin has two logbook dashboards, guided forms for the logbook of one run:

- **PLD logbook** for SA-PLD and LA-PLD runs;
- **Sputter logbook** for SPS runs (see [The sputter logbook](#the-sputter-logbook)).

They work the same way. Each saves the run as normal entries of this plugin's
schemas: an SA-PLD, LA-PLD or SPS logbook, plus a Sample entry for each new or
external sample. Everything they save can afterwards be viewed and edited in
NOMAD as usual; see [Use the PLD logbooks](use_this_plugin.md). This page
describes the PLD logbook first.

Compared with the NOMAD entry editor, the dashboards:

- start each run with the samples it makes or processes;
- show only the fields that apply to your choices (system, process steps, scan
  type, gases, plasma, in-situ techniques, ...);
- ask for the targets (and in the PLD logbook the laser details) only when a
  process step needs them;
- only save the logbook when **every required field** is filled in; until then
  the run can be kept as a [draft](#drafts-continue-on-another-computer);
- convert lab units (mbar, mJ, °C, mm, nm, ...) to the units NOMAD stores.

## Open it

Log in to NOMAD first. Then open **PLD logbook** or **Sputter logbook** from
NOMAD's dashboards menu, or go to
`<NOMAD URL>/dashboards/differ_pld4e_schemas-pld-logbook/` or
`<NOMAD URL>/dashboards/differ_pld4e_schemas-sputter-logbook/`
(locally: <http://localhost:8000/nomad-oasis/dashboards/differ_pld4e_schemas-pld-logbook/>).

It opens on the **start page**:

- **New logbook** starts an empty form.
- **Continue current logbook** returns to the logbook you were working on in this
  browser, whether saved or not.
- **Drafts** lists the drafts in your unpublished uploads; click one to continue it.
- **Recent logbooks** lists your latest logbooks; click one to open it.
  **Find a logbook…** searches all logbooks you can see.

Opening another logbook or draft asks first if it would replace a logbook you
are working on. **Start page** in the top bar (or a click on *PLD logbook*)
takes you back; the form stays as it is.

## Fill in a run

Work through the sections on the left; **Next** takes you to the next one. The
number next to a section is the number of things still missing there, and a
green tick means the section is complete. Missing fields are marked once you
leave a section with **Next**, or straight away for fields you have edited.

1. **Run.** Your name and email are filled in from your NOMAD login; change
   them if someone else does the run. Choose the PVD system: it decides which
   carriers, scan options and fields are offered. The date and start time are
   today and now unless you change them. The run name is optional.
2. **Samples.** List the samples you make or process in this run. Set *Number
   of new and external samples* to add or remove samples in one go. For each
   sample choose:
    - **New sample** (most runs): pick the substrate from the substrate
      database.
    - **External sample**: a sample prepared elsewhere, without a sample ID.
      Pick its substrate, or leave the substrate empty and describe it under
      *Substrate details*. Under *Films already on the sample* list the films it
      came with, from the substrate up (material and, if known, thickness). Put
      anything else you know about it in the comments.
    - **Existing sample**: a sample made earlier with a PLD4Energy system, e.g.
      for an extra deposition, annealing or only characterisation. Pick it from
      the list.

    Substrates are only chosen from the target and substrate database, which
    only maintainers can change (see
    [Set up the target and substrate database](use_this_plugin.md#set-up-the-target-and-substrate-database)).
    Is a substrate missing? Ask a maintainer. Maintainers see *New substrate
    in the database* below the samples; it asks for the material name and its
    chemical formula (e.g. `SrTiO3`), which makes the samples searchable by
    element, and saves it in the database upload. New and external samples get
    a **sample ID** `system_yyyy-mm-dd_hh:mm_S##` (S01, S02, ... in the order of
    the list) and a **sample name** made from the substrate and the films grown
    on it, e.g. `SrTiO3_YSZ-20nm_SrRuO3-50nm`. The films come from the
    deposition steps (see below), so the sample name changes once the (desired)
    film thickness is entered under *Process steps*. Existing
    samples keep their own ID.
3. **System details.** The substrate carrier and the base pressure of the main
   chamber. LA-PLD also asks for the particle reduction plate.
4. **Targets** and 5. **Laser details.** Only needed when a process step uses
   the laser (pre-ablation and deposition). Without such a step they show as
   *not needed* in the list on the left, and nothing entered there is saved.
    - Targets: pick each target in the system and its target number (its
      position, 1 to 5) for this run. The dashboard cannot add PLD targets: a
      maintainer adds a new target as a *PLD Target* entry in the target and
      substrate database upload in NOMAD, with its
      chemical formula, shape and size, density and the ID engraved on its back (see
      [Reference › PLD Target](../reference/references.md#pld-target)).
    - Laser details: enter the energies before and after the chamber. The 1st
      window transmission is calculated as you type; switch on *Enter the 1st
      window transmission manually* to type your own value instead.
6. **Process steps.** Add the steps in order with the *+ ...* buttons: pre-
   ablation, heating, annealing, pulsed laser deposition and cool-down. Each
   step can be moved up or down, removed, and folded away with a click on its
   title. A run without deposition (e.g. only annealing or only
   characterisation) is fine.
    - **Time:** the start and end time of each step, in 24-hour hh:mm (e.g.
      `14:05`; `1405` or `14.05` is turned into that), as in the system log, so
      the pressure, temperature, ... of the step can be found in the logs
      later. The date is that of the run; a time after midnight is taken as the
      next day. Both times are optional. A new step starts at the end time of
      the step before it; change it if there was a pause. An end time before
      the start time is an error. A step that starts before the step before it
      ends gets a warning, but can still be saved. A prefilled step or a
      recipe does not copy the times.
    - **Background gases:** choose *UHV* to record only the chamber pressure, or
      *Background gas* and tick each gas to fill in its set and read-out flow.
      All gases share one valve, so its position (0 closed to 1000 open) is
      entered once per step.
    - **Target stage:** start x, y and z position, offsets, scan width and scan
      speed in x and y.
    - **Temperature control** (heating, annealing, deposition and cool-down):
      the fields follow the *Temperature control* panel of the system
      software. Tick *Fix output* and *Drift compensation* as set there. A
      heating step also has *Ramp on*: its ramp rate is only asked for when
      the ramp is on. Annealing and cool-down steps always ask for the ramp
      rate. Deposition steps have no ramp.
      - SA-PLD: choose the **heating mode**. *Laser heating (PID)* takes the
        setpoint in °C and the ramp rate in °C/min, and asks for the heater
        output (%) once the setpoint is reached. *Laser heating (power)* takes
        the setpoint in % and the ramp rate in %/min. Also note the **laser
        output limitation** set with the knob (50% unless changed).
      - LA-PLD: setpoint in °C and ramp rate in °C/min, plus the set and
        actual voltage and current of the main heater power supply.
    - **Pulsed laser deposition:** a new deposition step starts with the target,
      target stage, gases and laser settings of the pre-ablation step before it;
      change what differs. Enter the **film thickness**, in nm or, with
      *Thickness given in* set to *pulses*, as a number of laser pulses (the
      sample name then shows e.g. `YSZ-1500p`). Each deposition step
      grows one film, of its target's material, on its samples, and these films
      make up the sample names. In the SA-PLD a deposition covers all samples
      loaded in the chamber; in the LA-PLD choose the sample. The target and
      heater stage fields follow the *Manual movement* and *Define scan
      pattern* dialogs of the system software; choose the heater scan type
      (*Polar scan* is the default) to get its scan fields.
7. **In-situ techniques.** Optional. For each measurement: *+ Add
   measurement*, choose the **sample**, tick the **process steps** it was taken
   during, then switch on each technique you used and add its data files. A file
   field takes several files of its format, e.g. a series of RHEED `.png`
   images. Files can also be added later: a technique without files is saved as
   *awaiting data*.
8. **System logfiles.** Optional: add the `.txt` logfiles exported from the
   TSST software.
9. **Review and save.** Lists everything that is still missing; click an item
   to jump to the field. Choose an upload (or *+ New upload*) and save.

Saving creates the Sample entries first and then the logbook, and shows
NOMAD's processing messages. After saving, the form stays open: saving again
updates the same logbook and its samples.

## Drafts: continue on another computer

A run often spans several computers, and a logbook can only be saved once it is
complete. To keep an unfinished run, use **Save draft** (top bar or *Review and
save*). It needs the system, date and start time, and an upload.

- The draft is stored in the upload as `pld_drafts/<run>.draft.json`
  (`sps_drafts/` for the sputter logbook), together
  with the in-situ files you picked. It is **not** an entry: it does not show up
  in searches and **does not count as logged**. Only the saved logbook does.
- On another computer, the start page lists the drafts in your unpublished
  uploads; pick one to carry on.
- If someone saved the same draft elsewhere after you opened it, you are asked
  whether to overwrite it or to load their version.
- Saving the complete logbook deletes the draft.

Independently of drafts, the form is kept in your browser while you work, so
you can close the page and continue later on the same computer. Files you chose
but did not save yet are not kept: choose them again. *New logbook* on the
start page clears the form.

## Export as PDF

**Export as PDF** (top bar, or *Review and save*) turns the logbook in the form
into a report and downloads it as a PDF file, named after the run. The report
lists every section and step with the values that apply, in lab units. Sections
the steps do not need are left out.

Any logbook can be exported, saved or not. Unless it is a complete logbook that
was saved to NOMAD, the report says **DRAFT / INCOMPLETE: this is not a logged
logbook** at the top, with the number of things still missing. The PDF is saved
on your computer only; the logbook in NOMAD remains the record.

## Add in-situ data later

In-situ data often has to be collected from other computers after the run. Save
the logbook without the files: the techniques show as *awaiting data* in the
dashboard and in NOMAD. Later, open the logbook from the start page, add the files under *In-situ
techniques* and save again. The same goes for the system logfiles.

Logbooks saved before measurements had a sample and process steps open with
their techniques as one measurement: choose its sample and steps before saving
again.

## Repeat a run (recipe)

Choose the PVD system, then under *Process steps* click **Load steps from a
recipe…** and pick an earlier logbook of the
same system. Its process steps are added after your current steps; if you have
not selected any targets yet, its targets are taken over too. Samples are not
copied: the steps apply to the samples of this run (in the LA-PLD, choose the
sample of each deposition step).

## Change a saved logbook

Opening a saved logbook from the start page loads it into the form. Saving overwrites it and
updates the Sample entries it created; samples from other runs are never
changed. A sample keeps its ID once its entry exists, even if you change the
date or time of the run. The logbook must be in an upload you can edit (not
published).

## The sputter logbook

The **Sputter logbook** is filled in like the PLD logbook, with these
differences:

1. **Run.** The PVD system is always *SPS*. Sample IDs are
   `SPS_yyyy-mm-dd_hh:mm_S##`.
2. **Samples.** As in the PLD logbook. The sample names come from the
   sputtering steps, e.g. `Si_Ta-50nm_Ti-10nm`.
3. **System details.** The substrate carrier (*4" carrier SPS*, *1 cm² sub
   plate* or *Fixed stage*) and the main chamber pressure. With the fixed stage,
   say whether a mask is used and which one.
4. **Targets.** Only needed when a step sputters (pre-sputtering or
   sputtering). Pick each target and its position: positions 1 and 2 take 2"
   targets, position 3 a 4" target. Targets come from the *sputter* target
   database, separate from the PLD targets. Maintainers see *New target in the
   database*, which asks for the chemical formula and the diameter in inch. NOMAD warns on save when a target does not fit its
   position.
5. **Process steps.** Pre-sputtering, heating, sputtering and cool-down. For a
   multilayer, add a pre-sputtering and sputtering step per layer.
    - **Plasma:** choose DC, RF or DC+RF. DC asks for the voltage U, RF for the
      load capacitance CL, DC+RF for both. The current I and the DC bias are
      optional; the power is required.
    - **Power ramps** (ramp up, ramp down) are entered in W per 5 minutes, as
      in the lab. NOMAD shows them in W/min: 10 W/5 min is 2 W/min.
    - **Sputtering:** a new sputtering step starts with the target, gases and
      plasma of the pre-sputtering step before it. Enter the heater position (x,
      y, z, spin), heater rotation, shutter, sputter time and the **film
      thickness**. A sputtering step covers all samples on the carrier.
6. **General comments.** Anything else about the run.

There is no laser and no in-situ section.

## Good to know

- Required fields are marked with `*`. Comments are optional.
- The dashboard checks the form again on the server before anything is saved.
- Targets and substrates come only from the target and substrate database
  upload; *View the database in NOMAD* (*Edit* for maintainers) opens it.
- New targets and substrates added to the database in NOMAD appear when you start a
  new logbook or open *Samples* or *Targets*; *Refresh lists* reloads them at
  any time.
- Targets and substrates that are switched off as *out of stock* in NOMAD are
  not offered. A logbook that already uses one keeps it, marked
  *(out of stock)*.
- A new logbook never overwrites an existing file: if a logbook with the same
  system, date, time and run name, or a sample with the same sample ID, already
  exists in the upload, saving stops with a message.
