# Use the PLD logbook dashboard

The **PLD logbook** dashboard is a guided form for the logbook of an SA-PLD or
LA-PLD run. It saves the run as normal entries of this plugin's schemas: an
SA-PLD or LA-PLD logbook, plus a Sample entry for each new or external sample.
Everything it saves can afterwards be viewed and edited in NOMAD as usual; see
[Use the PLD logbooks](use_this_plugin.md).

Compared with the NOMAD entry editor, the dashboard:

- starts each run with the samples it makes or processes;
- shows only the fields that apply to your choices (system, process steps, scan
  type, gases, in-situ techniques, ...);
- asks for the laser details and targets only when a process step needs the
  laser;
- only saves the logbook when **every required field** is filled in; until then
  the run can be kept as a [draft](#drafts-continue-on-another-computer);
- converts lab units (mbar, mJ, °C, mm, nm, ...) to the units NOMAD stores.

## Open it

Log in to NOMAD first. Then open **PLD logbook** from NOMAD's dashboards menu,
or go to `<NOMAD URL>/dashboards/differ_pld4e_schemas-pld-logbook/`
(locally: <http://localhost:8000/nomad-oasis/dashboards/differ_pld4e_schemas-pld-logbook/>).

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
    - **New sample** (most runs): pick the substrate from the list.
    - **External sample**: a sample prepared elsewhere, without a sample ID.
      Pick its substrate, or *Other* and describe it under *Substrate details*.
      Put anything else you know about it in the comments.
    - **Existing sample**: a sample made earlier with a PLD4Energy system, e.g.
      for an extra deposition, annealing or only characterisation. Pick it from
      the list.

    Under *Films grown in this run* add the films you will deposit, in order,
    with their material (from the target database) and thickness. New and
    external samples get a **sample ID** `system_yyyy-mm-dd_hh:mm_S##` (S01,
    S02, ... in the order of the list) and a **sample name** made from the
    substrate and films, e.g. `SrTiO3_YSZ-20nm_SrRuO3-50nm`. Both are shown as
    you type. Existing samples keep their own ID.
3. **System details.** The substrate carrier and the base pressure of the main
   chamber. LA-PLD also asks for the particle reduction plate.
4. **Targets** and 5. **Laser details.** Only needed when a process step uses
   the laser (pre-ablation and deposition). Without such a step they show as
   *not needed* in the list on the left, and nothing entered there is saved.
    - Targets: pick each target in the system and enter its target number for
      this run. A target that is not in the database yet can be added with
      *New target in the database*.
    - Laser details: enter the energies before and after the chamber. The 1st
      window transmission is calculated as you type; switch on *Enter the 1st
      window transmission manually* to type your own value instead.
6. **Process steps.** Add the steps in order with the *+ ...* buttons: pre-
   ablation, heating, annealing, pulsed laser deposition and cool-down. Each
   step can be moved up or down, removed, and folded away with a click on its
   title. A run without deposition (e.g. only annealing or only
   characterisation) is fine.
    - **Background gases:** choose *UHV* to record only the chamber pressure, or
      *Background gas* and tick each gas to fill in its set and read-out flow.
      All gases share one valve, so its position is entered once per step.
    - **Target stage:** start x, y and z position, offsets, scan width and scan
      speed in x and y.
    - **Heating and annealing:** note the heater output (%) once the setpoint is
      reached.
    - **Pulsed laser deposition:** a new deposition step starts with the target,
      target stage, gases and laser settings of the pre-ablation step before it;
      change what differs. In the SA-PLD a deposition covers all samples loaded
      in the chamber; switch on *Substrate stage scan* for its scan width and
      speed. In the LA-PLD choose the sample, and the heater scan type (*Polar
      scan* is the default).
7. **In-situ techniques.** Tick each technique you used. Add its data files now
   or later: a technique without files is saved as *awaiting data*.
8. **Review and save.** Lists everything that is still missing; click an item
   to jump to the field. Choose an upload (or *+ New upload*) and save.

Saving creates the Sample entries first and then the logbook, and shows
NOMAD's processing messages. After saving, the form stays open: saving again
updates the same logbook and its samples.

## Drafts: continue on another computer

A run often spans several computers, and a logbook can only be saved once it is
complete. To keep an unfinished run, use **Save draft** (top bar or *Review and
save*). It needs the system, date and start time, and an upload.

- The draft is stored in the upload as `pld_drafts/<run>.draft.json`, together
  with the in-situ files you picked. It is **not** an entry: it does not show up
  in searches and **does not count as logged**. Only the saved logbook does.
- On another computer, **Continue draft** lists the drafts in your unpublished
  uploads; pick one to carry on.
- If someone saved the same draft elsewhere after you opened it, you are asked
  whether to overwrite it or to load their version.
- Saving the complete logbook deletes the draft.

Independently of drafts, the form is kept in your browser while you work, so
you can close the page and continue later on the same computer. Files you chose
but did not save yet are not kept: choose them again. *New logbook* clears the
form.

## Add in-situ data later

In-situ data often has to be collected from other computers after the run. Save
the logbook without the files: the techniques show as *awaiting data* in the
dashboard and in NOMAD. Later, **Open logbook**, add the files under *In-situ
techniques* and save again.

## Repeat a run (recipe)

Choose the PVD system, then **Load recipe** and pick an earlier logbook of the
same system. Its process steps are added after your current steps; if you have
not selected any targets yet, its targets are taken over too. Samples are not
copied: the steps apply to the samples of this run (in the LA-PLD, choose the
sample of each deposition step).

## Change a saved logbook

**Open logbook** loads a saved logbook into the form. Saving overwrites it and
updates the Sample entries it created; samples from other runs are never
changed. A sample keeps its ID once its entry exists, even if you change the
date or time of the run. The logbook must be in an upload you can edit (not
published).

## Good to know

- Required fields are marked with `*`. Comments are optional.
- The dashboard checks the form again on the server before anything is saved.
- New targets added elsewhere in NOMAD appear when you start a new logbook or
  open *Samples* or *Targets*; *Refresh target list* reloads them at any time.
- A new logbook never overwrites an existing file: if a logbook with the same
  system, date, time and run name, or a sample with the same sample ID, already
  exists in the upload, saving stops with a message.
