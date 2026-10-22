# Install This Plugin

## In a local development setup (nomad-distro-dev)

Development happens in [`nomad-distro-dev`](https://github.com/FAIRmat-NFDI/nomad-distro-dev),
with the plugin checked out in `packages/differ-pld4energy-schemas`.

1. Make sure the root `pyproject.toml` of the distribution lists the plugin and
   its dependency `nomad-material-processing`:

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

2. Install: `uv sync`.
3. Start NOMAD: `uv run poe start`. The new entry types appear under
   *Create from schema* in an upload.

### When do changes show up?

| You changed | Do this |
| --- | --- |
| Python code of the schemas | Stop NOMAD and run `uv run poe start` again. |
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
your Oasis distribution, e.g. as a Git dependency:

```toml
dependencies = [
    "differ-pld4e-schemas @ git+https://github.com/timval-differ/DIFFER-PLD4E-schemas.git",
]
```

Then rebuild and restart the Oasis. Read the
[NOMAD plugin documentation](https://nomad-lab.eu/prod/v1/staging/docs/howto/oasis/plugins_install.html)
for the details.

The plugin registers two entry points:

| Entry point | What it adds |
| --- | --- |
| `differ_pld4e_schemas.schema_packages:schema_package_entry_point` | The schemas ("PLD4Energy Schemas") |
| `differ_pld4e_schemas.dashboards:pld_logbook_dashboard_entry_point` | The PLD logbook dashboard, at `<NOMAD URL>/dashboards/differ_pld4e_schemas-pld-logbook/` |
