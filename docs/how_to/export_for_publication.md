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

- every file of your upload; the data files (`.sp0`, `.csv`, images, ...) as
  they are;
- the archive files (`*.archive.json`, `*.archive.yaml`) with the data NOMAD
  stored for their entries when it processed them, not only what was saved in
  the file. What the plugins filled in, such as a spectrum read from its
  `.sp0` file and its plot, is in the ZIP as values. The files keep their names
  but are written as JSON;
- a copy of every entry your upload refers to in another upload, for example
  your targets and substrate types, in `referenced/<upload id>/` (and the
  entries those refer to, and so on);
- the references in the archive files rewritten to point at the files in the
  ZIP, so they keep working after the upload is published elsewhere;
- the schemas of the plugins your entries use, as
  [YAML schemas](https://docs.nomad-lab.eu/howto/schemas/define.html), one
  file per plugin in `schema/`: for example
  `schema/differ_pld4e_schemas.archive.yaml`, `schema/laeds_tools.archive.yaml`,
  and `schema/nomad_material_processing.archive.yaml` for the sections this
  plugin builds on. Every entry names its sections in them
  (`m_def: '../upload/raw/schema/differ_pld4e_schemas.archive.yaml#SAPLDLogbook'`),
  and together they rely on nothing but NOMAD itself.

Nothing in NOMAD is changed by an export.

## Publish on the central NOMAD

1. Log in at [nomad-lab.eu](https://nomad-lab.eu/prod/v1/gui/) with your own
   account and create a new upload.
2. Drop the ZIP into it. NOMAD unpacks and processes it.
3. Check the entries, add coauthors, a dataset and comments, and publish.

!!! note "The plugins' schemas on the central NOMAD"
    The central NOMAD runs none of the Oasis's plugins. It reads your
    logbooks, samples, targets and measurements with the YAML schemas in the
    ZIP, so they show there with their sections, values and descriptions. The
    schemas describe the data only: the plugins' code does not run there.
    What the plugins filled in on the Oasis is in the ZIP as values, but NOMAD
    does not fill in new values or make sample entries the way they do, and
    the logbook dashboards are not available. Data files are not parsed there
    either: their entries in the ZIP already hold what was read from them.

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
| *the section … is not in a schema of this NOMAD* | The entry uses a section of a plugin that is not installed in this Oasis (any more), or one that its version no longer has. |
| *names a definition of a plugin by its Python name outside an m_def* | A schema of your own (an `.archive.yaml` with `definitions:`) builds on a plugin's sections by their Python names, which the central NOMAD does not have. Only `m_def`s are rewritten; build your schema on NOMAD's own sections instead. |
| *NOMAD could not process this entry* | The entry failed when NOMAD processed it, so there is no data of it to export. Fix it (the entry's log in NOMAD says what went wrong), then export again. |
| *NOMAD stored no data for this entry* / *stored no archive* | The file has data, but NOMAD did not store any for its entry. Reprocess the upload, then export again. |
| *NOMAD has no entry for this file* | The archive file is not an entry of its own (for example it was added while the upload was processed). Reprocess the upload, then export again. |
| *The export was interrupted* | NOMAD was probably restarted during the export. Export again. |
| *The export failed unexpectedly* | Ask a maintainer to look for the error in NOMAD's log. |
