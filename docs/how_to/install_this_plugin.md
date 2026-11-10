# Install This Plugin

## In a local development setup (nomad-distro-dev)

Development happens in the lab's distribution,
[`timval-differ/nomad-distro-dev`](https://github.com/timval-differ/nomad-distro-dev),
a fork of FAIRmat-NFDI's [`nomad-distro-dev`](https://github.com/FAIRmat-NFDI/nomad-distro-dev)
(its `upstream`; that one does not contain this plugin). The plugin is checked
out in `packages/differ-pld4energy-schemas`. The distribution's README has the
full instructions; in short:

1. Clone the distribution with its submodules (NOMAD itself in
   `packages/nomad-FAIR`, this plugin and `nomad-material-processing`):
   `git clone --recurse-submodules https://github.com/timval-differ/nomad-distro-dev.git`,
   or `git submodule update --init --recursive` in an existing clone.
2. Start the services NOMAD needs (Docker) and write its configuration:
   `uv run poe setup`.
3. The lab's distribution already lists the plugin and its dependency
   `nomad-material-processing` in its root `pyproject.toml`; in another
   distribution, add them:

    ```toml
    [project]
    dependencies = [
        "differ-pld4e-schemas",
        "nomad-material-processing",
        # ...
    ]

    [tool.uv.sources]
    differ-pld4e-schemas = { workspace = true }
    nomad-material-processing = { workspace = true }
    ```

4. Install: `uv sync`. The plugin needs Python 3.11 or newer, `nomad-lab` 2.0.x
   (2.0.1 or newer) and `nomad-material-processing` 1.0.x (1.0.7 or newer). The
   distribution's own `requires-python` must not allow an older Python.
5. Set the target and substrate database upload in the distribution's
   `nomad.yaml` (`database_upload_id`, see
   [Set up the target and substrate database](use_this_plugin.md#set-up-the-target-and-substrate-database)).
   Without it the dashboards cannot offer targets or substrates.
6. Start NOMAD: `uv run poe start`. The new entry types appear under
   *Create from schema* in an upload, and the dashboards under *Dashboards*.
7. For the dashboards' scripts: install Node 22 or newer and run `npm ci` in
   the plugin folder (see [Contribute to this plugin](contribute_to_this_plugin.md#develop-and-test)).

### When do changes show up?

| You changed | Do this |
| --- | --- |
| Python code of the schemas | Stop NOMAD and run `uv run poe start` again. |
| A dashboard: its Python code or its page (`dashboards/common/static/`) | Restart NOMAD, then reload the page. The page asks for a restart until NOMAD runs the same version as its files. |
| `nomad.yaml` (e.g. `database_upload_id`) | Restart NOMAD. |
| `pyproject.toml` (dependencies, entry points) | `uv sync`, then restart. |
| A new package in `packages/` | Add it to `pyproject.toml`, `uv sync`, then restart. |

Entries that were processed with an older version of the schema are not updated
automatically. Save them again in the form, or reprocess the upload.

!!! warning "Every folder in `packages/` must be a Python project"
    The distribution uses `packages/*` as a uv workspace. A folder there without a
    `pyproject.toml` makes every `uv` command fail with
    `Workspace member ... is missing a pyproject.toml`.

## In a NOMAD Oasis

Add the plugin (and `nomad-material-processing`) to the plugin dependencies of
your Oasis distribution, e.g. as a Git dependency on a released version (a tag),
so that a rebuild installs the version you tested and not whatever `main` is
then:

```toml
dependencies = [
    "differ-pld4e-schemas @ git+https://github.com/timval-differ/differ-pld4energy-schemas.git@v4.0.0",
]
```

The plugin needs nomad-lab 2.0.x and nomad-material-processing 1.0.x
(`pyproject.toml`).

Then rebuild and restart the Oasis. Read the
[NOMAD plugin documentation](https://nomad-lab.eu/prod/v1/staging/docs/howto/oasis/plugins_install.html)
for the details.

The plugin registers three entry points:

| Entry point | What it adds |
| --- | --- |
| `differ_pld4e_schemas.schema_packages:schema_package_entry_point` | The schemas ("PLD4Energy Schemas") |
| `differ_pld4e_schemas.dashboards:pld_logbook_dashboard_entry_point` | The PLD logbook dashboard, at `<NOMAD URL>/dashboards/differ_pld4e_schemas-pld-logbook/` |
| `differ_pld4e_schemas.dashboards:sputter_logbook_dashboard_entry_point` | The sputter logbook dashboard, at `<NOMAD URL>/dashboards/differ_pld4e_schemas-sputter-logbook/` |
