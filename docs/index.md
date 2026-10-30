# Welcome to the `DIFFER-PLD4E-schemas` documentation

A NOMAD plugin with the electronic lab notebook (ELN) schemas of the PLD4Energy
lab at DIFFER.

## Introduction

The plugin adds these entry types to NOMAD:

| Entry type | Use it for |
| --- | --- |
| **SA-PLD Logbook** | One run on the SA-PLD system: the samples it makes or processes, system details, laser calibration, targets, process steps and in-situ data. |
| **LA-PLD Logbook** | One run on the LA-PLD system. Same as SA-PLD, plus the larger carriers, the particle reduction plate and polar/cartesian heater scans. |
| **PLD Target** | One physical target (the target database). |
| **Sample** | One sample: a substrate with the films grown on it, with its sample ID. Usually created for you by a logbook; not specific to PLD. |
| **PLD In-situ Techniques** | In-situ measurements (RHEED, MIC, SE, LA-EDS, OES, SHG) that are not part of a new deposition run, e.g. post-processing of an older sample. |
| **Deposition** | A sputter deposition run (the original sputter schemas of this plugin). |

It also adds the **PLD logbook dashboard**: a guided form for SA-PLD and LA-PLD
runs that starts from the samples, shows only the fields that apply, and only
saves complete logbooks (unfinished runs can be kept as drafts).
See [Use the PLD logbook dashboard](how_to/use_the_dashboard.md).

<div markdown="block" class="home-grid">
<div markdown="block">

### Tutorial

Record your first PLD run from start to finish.

- [Tutorial: your first SA-PLD run](tutorial/tutorial.md)

</div>
<div markdown="block">

### How-to guides

Step-by-step instructions for specific tasks:

- [Use the PLD logbooks](how_to/use_this_plugin.md)
- [Use the PLD logbook dashboard](how_to/use_the_dashboard.md)
- [Reproduce a run with a recipe](how_to/reuse_a_recipe.md)
- [Install this plugin](how_to/install_this_plugin.md)
- [Contribute to this plugin](how_to/contribute_to_this_plugin.md)
- [Contribute to the documentation](how_to/contribute_to_the_documentation.md)

</div>

<div markdown="block">

### Explanation

How the schemas are put together and why: entries and references, generated
(read-only) fields, units and calculations.

- [Explanation](explanation/explanation.md)

</div>
<div markdown="block">

### Reference

Every section and field, with its unit and whether you can edit it.

- [Reference](reference/references.md)

</div>
</div>
