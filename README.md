# DIFFER-PLD4E-schemas

NOMAD schemas for the electronic lab notebook of the PLD4Energy lab at DIFFER.

**PLD logbooks.** The `SA-PLD Logbook` and `LA-PLD Logbook` entry types record
one pulsed laser deposition run each: laser calibration (with the automatic 1st
window transmission), the samples made or processed, the targets used, the process steps
(pre-ablation, heating, annealing, deposition, cool-down, with background gases, laser
settings and stage positions) and in-situ data (RHEED, MIC, SE, LA-EDS, OES,
SHG). Targets (`PLD Target`) and samples (`Sample`) are separate
entries that the logbooks refer to. An earlier logbook can be used as a recipe
to repeat a run on other samples. In-situ measurements outside a run go in a
`PLD In-situ Techniques` entry.

**SPS logbook.** The `SPS Logbook` entry type records one run in the SPS
sputter system, built like the PLD logbooks: the samples made or processed, the
substrate carrier (and mask), the targets in positions 1 to 3 and the process
steps (pre-sputtering, heating, sputtering, cool-down, with background gases,
the DC/RF plasma, power ramps and the heater position). Its targets are
`Sputter Target` entries; samples and substrate types are shared with PLD.

**Logbook dashboards.** Guided forms served by NOMAD, for SA-PLD and LA-PLD
runs at `<NOMAD URL>/dashboards/differ_pld4e_schemas-pld-logbook/` and for SPS
runs at `<NOMAD URL>/dashboards/differ_pld4e_schemas-sputter-logbook/`. They
start each run from its samples, show only the fields that apply to the choices
made (system, process steps, scan type, gases, plasma, in-situ techniques),
save only complete logbooks (unfinished runs can be kept as drafts), and write
them as entries of the schemas above. See
[Use the logbook dashboards](docs/how_to/use_the_dashboard.md).

See the [documentation](docs/index.md): a tutorial, how-to guides (including
[recipes](docs/how_to/reuse_a_recipe.md)), an explanation of the design and a
field reference. Example entries are in `tests/data/`.

## Development

New to the code? Read [Plugin structure](docs/explanation/plugin_structure.md)
first: it maps the parts of the plugin (schemas and dashboards, server and
page), what is checked where, the tests and CI, and where to make a change.
[Contribute to this plugin](docs/how_to/contribute_to_this_plugin.md) has the
recipes for common changes.

The plugin is developed inside the lab's distribution,
[`timval-differ/nomad-distro-dev`](https://github.com/timval-differ/nomad-distro-dev)
(a fork of FAIRmat-NFDI's `nomad-distro-dev`), checked out in
`packages/differ-pld4energy-schemas`; see
[Install this plugin](docs/how_to/install_this_plugin.md). It needs Python 3.10
or newer and `nomad-lab` 2.0 or newer; [uv](https://docs.astral.sh/uv/) manages
the environment. The dashboards' browser code is type-checked and tested with
Node 22 or newer (no build step: the browser loads the files as they are).

The example archives in `tests/data/` leave out the references to substrates and targets. Add references to existing NOMAD entries before uploading.

### Run the tests

From the plugin folder:
```sh
uv run pytest                     # Python: schemas and dashboards
npm ci                            # once, and after package-lock.json changes
npm run typecheck && npm test     # the dashboards' scripts
```

To measure the coverage of the plugin's code by the Python tests:
```sh
uv run --with coverage coverage run --source=src -m pytest && uv run --with coverage coverage report
```

### Run linting and auto-formatting

We use [Ruff](https://docs.astral.sh/ruff/) for linting and formatting the code; CI runs `ruff check`. You can run locally:
```sh
uv run ruff check src tests
uv run ruff format src tests
```

### Debugging

For interactive debugging of the tests, use `pytest` with the `--pdb` flag. We recommend using an IDE for debugging, e.g., _VSCode_. If that is the case, add the following snippet to your `.vscode/launch.json`:
```json
{
  "configurations": [
      {
        "name": "<descriptive tag>",
        "type": "debugpy",
        "request": "launch",
        "cwd": "${workspaceFolder}",
        "module": "pytest",
        "justMyCode": true,
        "env": {
            "_PYTEST_RAISE": "1"
        },
        "args": [
            "-sv",
            "--pdb",
            "<path-to-plugin-tests>",
        ]
    }
  ]
}
```

where `<path-to-plugin-tests>` must be changed to the local path to the test module to be debugged.

The settings configuration file `.vscode/settings.json` automatically applies the linting and formatting upon saving the modified file.

### Documentation on Github pages

To view the documentation locally (the docs tools are in the `dev` extras):
```sh
uv run --extra dev mkdocs serve -a 127.0.0.1:8001   # NOMAD uses port 8000
```

It is published to GitHub Pages on every push to `main`. See
[Contribute to the documentation](docs/how_to/contribute_to_the_documentation.md).

## Adding this plugin to NOMAD

Currently, NOMAD has two distinct flavors that are relevant depending on your role as an user:
1. [A NOMAD Oasis](#adding-this-plugin-in-your-nomad-oasis): any user with a NOMAD Oasis instance.
2. [Local NOMAD installation and the source code of NOMAD](#adding-this-plugin-in-your-local-nomad-installation-and-the-source-code-of-nomad): internal developers.

### Adding this plugin in your NOMAD Oasis

Read the [NOMAD plugin documentation](https://nomad-lab.eu/prod/v1/staging/docs/howto/oasis/plugins_install.html) for all details on how to deploy the plugin on your NOMAD instance.

### Adding this plugin in your local NOMAD installation and the source code of NOMAD

We now recommend using the dedicated [`nomad-distro-dev`](https://github.com/FAIRmat-NFDI/nomad-distro-dev) repository to simplify the process. Please refer to that repository for detailed instructions.

## Publish note
In the [GitHub actions workflow](./.github/workflows/publish.yml) for publishing the DIFFER-PLD4E-schemas plugin to PyPI, we commented out the `deploy` job . If you want to publish the plugin to `PyPI`, you need to set up your project in `PyPI`. There are several online tutorials on publishing a Python package to PyPI, e.g., [How to Publish a Python Package to PyPI](https://realpython.com/pypi-publish-python-package/). After that, you can uncomment the `deploy` job in the workflow file and push the changes to GitHub. The workflow will be triggered and the package will be published to `PyPI` when you create a new release on GitHub.

### Template update

We use [`cruft`](https://github.com/cruft/cruft) to update the project based on template changes. To run the check for updates locally, run `cruft update` in the root of the project. More details see the instructions on [`cruft` website](https://cruft.github.io/cruft/#updating-a-project).

## Main contributors
| Name | E-mail     |
|------|------------|
| Tim van Alphen | [t.j.j.vanalphen@differ.nl](mailto:t.j.j.vanalphen@differ.nl)
