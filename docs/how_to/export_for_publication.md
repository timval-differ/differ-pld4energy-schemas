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
  upload is published elsewhere.

Nothing in NOMAD is changed by an export.

## Publish on the central NOMAD

1. Log in at [nomad-lab.eu](https://nomad-lab.eu/prod/v1/gui/) with your own
   account and create a new upload.
2. Drop the ZIP into it. NOMAD unpacks and processes it.
3. Check the entries, add coauthors, a dataset and comments, and publish.

!!! note "This plugin's schemas on the central NOMAD"
    The central NOMAD does not run this plugin. Until it can read the schemas
    of plugins from the uploads themselves (planned for NOMAD 2.1), your
    logbooks, samples and targets show there as files and entries without their
    PLD4Energy sections.

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
| *The upload has files in "referenced/"* | That folder name is used for the copied entries. Rename the folder in your upload. |
| *The export was interrupted* | NOMAD was probably restarted during the export. Export again. |
| *The export failed unexpectedly* | Ask a maintainer to look for the error in NOMAD's log. |
