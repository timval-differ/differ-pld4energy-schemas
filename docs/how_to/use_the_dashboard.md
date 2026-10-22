# Use the PLD logbook dashboard

The **PLD logbook** dashboard is a guided form for the logbook of an SA-PLD or
LA-PLD run. It saves the run as normal entries of this plugin's schemas: an
SA-PLD or LA-PLD logbook, plus a PLD Substrate entry for each new substrate.
Everything it saves can afterwards be viewed and edited in NOMAD as usual; see
[Use the PLD logbooks](use_this_plugin.md).

Compared with the NOMAD entry editor, the dashboard:

- shows only the fields that apply to your choices (system, scan type, gases,
  in-situ techniques, ...);
- only saves the logbook when **every required field** is filled in;
- converts lab units (mbar, mJ, °C, mm, ...) to the units NOMAD stores.

## Open it

Log in to NOMAD first. Then open **PLD logbook** from NOMAD's dashboards menu,
or go to `<NOMAD URL>/dashboards/differ_pld4e_schemas-pld-logbook/`
(locally: <http://localhost:8000/nomad-oasis/dashboards/differ_pld4e_schemas-pld-logbook/>).

## Fill in a run

Work through the sections on the left; **Next** takes you to the next one. The
number next to a section is the number of things still missing there, and a
green tick means the section is complete. Missing fields are marked once you
leave a section with **Next**, or straight away for fields you have edited.

1. **System details.** Choose the PVD system first: it decides which carriers,
   scan options and fields are offered. LA-PLD also asks for the particle
   reduction plate.
2. **Laser details.** Enter the energies before and after the chamber. The 1st
   window transmission is calculated as you type; switch on *Enter the 1st
   window transmission manually* to type your own value instead.
3. **Targets.** Pick each target in the system and enter its target number for
   this run. A target that is not in the database yet can be added with
   *New target in the database*.
4. **Substrates.** Create the substrates of this run (the sample user ID is
   shown as you type), or pick an existing substrate, e.g. for post-processing.
5. **Process steps.** Add the steps in order with the *+ ...* buttons. Each step
   can be moved up or down, removed, and folded away with a click on its title.
   The target and substrate of a step are chosen from the targets and
   substrates above, so they always match. At least one pulsed laser deposition
   step is required.
    - Tick a background gas to fill in its set flow, read-out flow, valve
      position and whether the valve was fixed.
    - SA-PLD: switch on *Substrate stage scan* for the cartesian scan fields.
    - LA-PLD: choose the heater scan type; *Polar scan* is the default.
6. **In-situ techniques.** Tick each technique you used and add at least one of
   its files. Files are uploaded when you save.
7. **Review and save.** Lists everything that is still missing; click an item
   to jump to the field. Choose an upload (or *+ New upload*) and save.

Saving creates the PLD Substrate entries first and then the logbook, and shows
NOMAD's processing messages. After saving, the form stays open: saving again
updates the same logbook.

## Your draft

The form is kept in your browser while you work, so you can close the page and
continue later on the same computer. Files you chose but did not save yet are
not kept: choose them again. *New logbook* clears the form.

## Repeat a run (recipe)

Choose the PVD system, then **Load recipe** and pick an earlier logbook of the
same system. Its process steps are added after your current steps; if you have
not selected any targets yet, its targets are taken over too. Substrates are not
copied: choose the substrate in each deposition step.

## Change a saved logbook

**Open logbook** loads a saved logbook into the form. Saving overwrites it.
Substrates that already have an entry are not created again. The logbook must
be in an upload you can edit (not published).

## Good to know

- Required fields are marked with `*`. Comments are optional.
- The dashboard checks the form again on the server before anything is saved.
- A new logbook never overwrites an existing file: if a logbook with the same
  system, date and run name, or a substrate with the same sample user ID,
  already exists in the upload, saving stops with a message.
