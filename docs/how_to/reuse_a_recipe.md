# Reproduce a run with a recipe

A **recipe** is the list of process steps of an earlier run, with all their
parameters: pre-ablation, heating, annealing, deposition and cool-down steps,
with gases, pressures, temperatures, laser settings and stage positions. Loading
a recipe copies those steps into the logbook you are working on, so you can run
the same process again on the samples of this run.

There is no separate "recipe" entry type: **any earlier logbook of the same PLD
system is a recipe**. Name your logbooks clearly so you can find good recipes
later.

## When to use it

- Repeat a deposition on a new sample.
- Make a series of samples with the same process and change one parameter each time.
- Run the same process on an existing sample again, e.g. a post-processing step.

## Steps

1. Create the new logbook (**SA-PLD Logbook** or **LA-PLD Logbook**, the same
   type as the recipe) and fill in the system details, laser details and targets
   as usual.
2. Add the samples under **samples** and **save**. This creates the Sample
   entries the recipe will be applied to. An existing sample is added as
   `Existing sample`.
3. Open **load recipe** and fill in:
    - **recipe**: the earlier logbook to copy from;
    - **sample** (optional): one sample to link the copied deposition steps to.
      If you leave it empty, the deposition steps are linked to all samples of
      this logbook;
    - tick **apply recipe**.
4. **Save.**

The steps of the recipe are now added to **steps**. **Apply recipe** is unticked
again and **applied recipe** shows the name of the recipe that was used.

5. Go through the copied steps and change whatever is different in this run
   (see [After applying](#after-applying)), then save again.

## What is copied

| Part of the recipe | Copied? | Notes |
| --- | --- | --- |
| Process steps | yes | All steps, in order, with all their sub-sections (gases, laser, target stage, heater stage position, scans). |
| Samples of the deposition steps | **no** | Replaced by the sample chosen in **load recipe**, or all samples of this logbook. The recipe's own samples are never copied, so the new run cannot accidentally be recorded on the old samples. |
| Target of each step | yes | Steps keep pointing to the same PLD Target entries as in the recipe. |
| Target details | only if empty | If this logbook has no targets yet, the recipe's targets (including their target numbers) are copied. If you already selected targets, they are kept as they are. |
| Target number in the steps | recalculated | Taken from **this** logbook's target details on save. |
| Step name, start time, duration, comments | yes | Update start times and comments for the new run. |
| Laser details (calibration) | no | Calibrate the laser for every run. |
| System details (date, base pressure, carrier, particle reduction plate) | no | |
| Samples | no | |
| In-situ techniques | no | |

The copy is a snapshot. Changing the recipe logbook later does not change the
logbooks it was applied to. The **recipe** field keeps the link to the recipe,
so you can always see where the steps came from.

## After applying

Check after every recipe:

- **Targets.** If the recipe uses a target that is not in this logbook's target
  details, the step gives a warning on save and its target number stays empty.
  Add the target under **targets**, or pick another target in the step.
- **Target numbers.** Targets move, so check the target numbers in the target
  details. The steps take their target number from there.
- **Samples.** All copied deposition steps are linked to the same samples. In
  an LA-PLD logbook with several samples, change the sample of the steps that
  belong to another sample.
- **Start times and comments** are those of the recipe run.

## Things to know

- **Same system only.** An SA-PLD recipe can only be applied to an SA-PLD
  logbook and an LA-PLD recipe only to an LA-PLD logbook: the step types differ.
  Selecting a recipe of the other system gives an error and nothing is copied.
  The recipe picker may also list other process entries, such as sputter
  depositions. Choose a PLD logbook.
- **Steps are added, not replaced.** Steps already in the logbook stay and the
  recipe steps are added after them. Delete steps you don't need.
- **Applying twice adds the steps twice.** **Apply recipe** is unticked after
  each copy, so saving again does not copy again. But if you tick it again,
  the steps are added a second time.
- **No recipe or no samples.** Without a recipe, ticking **apply recipe** gives
  an error. Without samples (none chosen and none in this logbook), the steps
  are copied and their samples stay empty. Fill them in afterwards.

## Example: a series on new samples

Run 1 is the reference run, `STO on Si`. For run 2:

1. Create an **SA-PLD Logbook** `STO on Si (repeat)`, fill in date, base pressure,
   carrier and laser details.
2. Add a new sample on `Si 1" with flat` with a 20 nm SrTiO3 film, and save.
   This creates `SA-PLD_<date>_<time>_S01`.
3. Under **load recipe** select `STO on Si`, leave **sample** empty, tick
   **apply recipe** and save.
4. All steps of run 1 are now in run 2. Their deposition steps are linked to
   `SA-PLD_<date>_<time>_S01`, and the targets of run 1 are selected. Change the
   target numbers if the targets moved, and change the number of pulses if
   this sample should be thicker.

## In an archive file

You can also apply a recipe from a YAML or JSON archive file. A logbook in the
same upload is referenced by its file name:

```yaml
data:
  m_def: differ_pld4e_schemas.schema_packages.schema_package.SAPLDLogbook
  name: STO on Si (repeat)
  load_recipe:
    recipe: '../upload/archive/mainfile/sto_on_si.archive.yaml#data'
    apply_recipe: true
```
