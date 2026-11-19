# Export an upload for publication

Your logbooks and samples refer to targets and substrate types in the
[target and substrate database](use_this_plugin.md#set-up-the-target-and-substrate-database),
an upload of its own that only the maintainers can change. Published on the
central NOMAD on its own, your upload would refer to entries that are not
there. The **Export for publication** dashboard makes one ZIP that holds your
upload together with every entry it refers to, ready to publish on the central
NOMAD.

## Export

1. Open `<NOMAD URL>/dashboards/differ_pld4e_schemas-publication/`, or find
   **Export for publication** among the dashboards in NOMAD. You must be
   logged in to NOMAD.
2. Choose the upload. The list holds your uploads, newest first. A link can
   choose one for you: add `?upload_id=<upload id>` to the address.
3. Click **Export**. The export runs on the server; keep the page open while
   it does. A large upload can take a minute. You can run one export at a
   time, and an upload that NOMAD is still processing cannot be exported yet.
4. Click **Download** to save the ZIP (`<upload id>-publication.zip`). It is
   kept for one day; export again to get it later.

The ZIP holds:

- every file of your upload, as it is;
- a copy of every entry your upload refers to in another upload, for example
  your targets and substrate types, in `referenced/<upload id>/` (and the
  entries those refer to, and so on);
- the references in the archive files (`*.archive.json`, `*.archive.yaml`)
  rewritten to point at the files in the ZIP, so they keep working after the
  upload is published elsewhere;
- this plugin's schemas as a [YAML schema](https://docs.nomad-lab.eu/howto/schemas/define.html),
  `schema/differ_pld4e_schemas.archive.yaml`, with every entry naming its
  sections in it (`m_def: '../upload/raw/schema/differ_pld4e_schemas.archive.yaml#SAPLDLogbook'`).
  The schema includes the sections of nomad-material-processing that this
  plugin builds on, so it relies on nothing but NOMAD itself.

Nothing in NOMAD is changed by an export.

## Publish on the central NOMAD

1. Log in at [nomad-lab.eu](https://nomad-lab.eu/prod/v1/gui/) with your own
   account and create a new upload.
2. Drop the ZIP into it. NOMAD unpacks and processes it.
3. Check the entries, add coauthors, a dataset and comments, and publish.

!!! note "This plugin's schemas on the central NOMAD"
    The central NOMAD runs neither this plugin nor nomad-material-processing.
    It reads your logbooks, samples and targets with the YAML schema in the
    ZIP, so they show there with their PLD4Energy sections, values and
    descriptions. The schema
    describes the data only: the plugin's code does not run there. NOMAD does
    not fill in values or make sample entries the way the plugin does, and the
    logbook dashboards are not available. What the Oasis made before the export
    is in the ZIP as it is.

## When the export fails

The export is not made if any reference cannot be kept working. The page then
lists every problem, each with the file it is in:

| Message | What to do |
| --- | --- |
| *points at an entry of upload … that does not exist or that you cannot see* | The entry was deleted, or it is in an upload that is not shared with you (for example a sample of a colleague). Ask its owner to add you as a reviewer, or change the reference. |
| *Cannot read upload …* | The same, for a whole upload. |
| *points at an entry in another NOMAD* | The reference is to another NOMAD installation; such entries cannot be copied. |
| *NOMAD cannot refer to a file with "?", "#", "\" or "mainfile/" in its name* | Rename the file (or its folder), then export again. |
| *is a kind of reference that the export cannot rewrite* | The reference names an entry by `/entries/<id>/…` or points into the raw files of another upload. Change it to a normal reference to the entry. |
| *The upload has files in "referenced/"* (or *"schema/"*) | That folder name is used for the copied entries (or the schema). Rename the folder in your upload. An upload made from an exported ZIP has both already: export the original upload instead. |
| *the section … is not in the schemas of this plugin* | The entry uses a section of another plugin, or one that this version of the plugin no longer has. Only this plugin's sections and NOMAD's own can be exported. |
| *names a definition of this plugin by its Python name outside an m_def* | A schema of your own (an `.archive.yaml` with `definitions:`) builds on this plugin's sections by their Python names, which the central NOMAD does not have. Only `m_def`s are rewritten; build your schema on NOMAD's own sections instead. |
| *The export was interrupted* | NOMAD was probably restarted during the export. Export again. |
| *The export failed unexpectedly* | Ask a maintainer to look for the error in NOMAD's log. |
