# Reproduce a run with a recipe

A **recipe** is the list of process steps of an earlier run, with all their
parameters: pre-ablation, heating, deposition and cool-down steps, with gases,
pressures, temperatures, laser settings and stage positions. Loading a recipe
copies those steps into the logbook you are working on, so you can run the same
process again on a substrate of your choice.

There is no separate "recipe" entry type: **any earlier logbook of the same PLD
system is a recipe**. Name your logbooks clearly so you can find good recipes
later.

## When to use it

- Repeat a deposition on a fresh substrate.
- Make a series of samples with the same process and change one parameter each time.
- Run the same process on an existing sample again, e.g. a post-processing step.

## Steps

1. Create the new logbook (**SA-PLD Logbook** or **LA-PLD Logbook**, the same
   type as the recipe) and fill in the system details, laser details and targets
   as usual.
2. Add the substrate under **substrates** and **save**. This creates the
   PLD Substrate entry the recipe will be applied to. If you want to use an
   existing substrate instead, skip this step.
3. Open **load recipe** and fill in:
    - **recipe**: the earlier logbook to copy from;
    - **substrate** (optional): the substrate to link the copied deposition steps
      to. If you leave it empty, the first substrate created in this logbook is used;
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
| Substrate of the deposition steps | **no** | Replaced by the substrate you chose in **load recipe**. The recipe's own substrate is never copied, so the new run cannot accidentally be recorded on the old sample. |
| Target of each step | yes | Steps keep pointing to the same PLD Target entries as in the recipe. |
| Target details | only if empty | If this logbook has no targets yet, the recipe's targets (including their target numbers) are copied. If you already selected targets, they are kept as they are. |
| Target number in the steps | recalculated | Taken from **this** logbook's target details on save. |
| Step name, start time, duration, comments | yes | Update start times and comments for the new run. |
| Laser details (calibration) | no | Calibrate the laser for every run. |
| System details (date, base pressure, carrier, particle reduction plate) | no | |
| Substrates | no | |
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
- **Substrate.** All copied deposition steps are linked to one substrate. For a
  logbook with several substrates, change the substrate in the steps that
  belong to another substrate.
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
- **No recipe or no substrate.** Without a recipe, ticking **apply recipe** gives
  an error. Without a substrate (none chosen and none created in this logbook),
  the steps are copied and their substrate stays empty. Fill it in afterwards.

## Example: a series on new substrates

Run 1 is the reference run, `STO on Si`. For run 2:

1. Create an **SA-PLD Logbook** `STO on Si (repeat)`, fill in date, base pressure,
   carrier and laser details.
2. Add substrate run `2`, sample `1`, and save. This creates
   `SA-PLD_<date>_2_1`.
3. Under **load recipe** select `STO on Si`, leave **substrate** empty, tick
   **apply recipe** and save.
4. All steps of run 1 are now in run 2. Their deposition steps are linked to
   `SA-PLD_<date>_2_1`, and the targets of run 1 are selected. Change the
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
