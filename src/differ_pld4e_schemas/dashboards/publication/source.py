"""
The uploads of this NOMAD, read on the server as one user (see
`differ_pld4e_schemas.snapshot.Source`).

Every upload is checked with NOMAD's own rule for reading an upload before
anything of it is read: the export must not hand out files of an upload the
user cannot see, such as another researcher's referenced sample. The files, and
the archives NOMAD stored when processing them, are then read as NOMAD's API
reads them (`upload.upload_files`).

NOMAD's server modules (MongoDB and all) are imported only when used, so that
the plugin and its tests also load with NOMAD installed without its
infrastructure extras, as in CI; the tests pass their own `read_access` and
`entries`.
"""

from __future__ import annotations

from fastapi import HTTPException

from differ_pld4e_schemas.snapshot import SnapshotError


def nomad_read_access(upload_id: str, user):
    """
    The upload, if `user` may read it, by NOMAD's rule for the raw-file API
    (published uploads included); else HTTPException 404 or 403.
    """
    from nomad.app.v1.routers.uploads.utils import get_upload_with_read_access

    return get_upload_with_read_access(upload_id, user, include_others=True)


def nomad_entries(upload_id: str):
    """The entries of an upload, with their files."""
    from nomad.processing import Entry

    return Entry.objects(upload_id=upload_id).only(
        'entry_id', 'mainfile', 'mainfile_key', 'process_status'
    )


class NomadFilesSource:
    def __init__(self, user, read_access=nomad_read_access, entries=nomad_entries):
        self.user = user
        self.read_access = read_access
        self.entries = entries
        self._uploads: dict = {}
        self._entries: dict[str, dict] = {}

    def _upload(self, upload_id: str):
        if upload_id not in self._uploads:
            try:
                self._uploads[upload_id] = self.read_access(upload_id, self.user)
            except HTTPException as error:
                raise SnapshotError(
                    f'Cannot read upload {upload_id}: {error.detail}'
                ) from error
        return self._uploads[upload_id]

    def raw_files(self, upload_id: str) -> dict[str, bytes]:
        files = self._upload(upload_id).upload_files
        try:
            result = {}
            for info in files.raw_listdir(recursive=True, files_only=True):
                with files.raw_file(info.path, 'rb') as file:
                    result[info.path] = file.read()
            return result
        finally:
            files.close()

    def raw_file(self, upload_id: str, path: str) -> bytes:
        files = self._upload(upload_id).upload_files
        try:
            with files.raw_file(path, 'rb') as file:
                return file.read()
        except KeyError as error:
            raise SnapshotError(
                f'Cannot read "{path}" of upload {upload_id}: no such file.'
            ) from error
        finally:
            files.close()

    def _entries_by_file(self, upload_id: str) -> dict:
        """The entries of the upload, by file."""
        self._upload(upload_id)  # the access check
        if upload_id not in self._entries:
            # An entry made from part of a file cannot be named by its file.
            self._entries[upload_id] = {
                entry.mainfile: entry
                for entry in self.entries(upload_id)
                if not entry.mainfile_key
            }
        return self._entries[upload_id]

    def mainfiles(self, upload_id: str) -> dict[str, str]:
        return {
            entry.entry_id: mainfile
            for mainfile, entry in self._entries_by_file(upload_id).items()
        }

    def processed_data(self, upload_id: str, mainfile: str) -> dict | None:
        from nomad.archive import to_json
        from nomad.models.common import ProcessStatus

        entry = self._entries_by_file(upload_id).get(mainfile)
        if entry is None:
            raise SnapshotError(
                f'{mainfile}: NOMAD has no entry for this file of upload {upload_id}.'
            )
        if entry.process_status in ProcessStatus.STATUSES_PROCESSING:
            raise SnapshotError(
                f'{mainfile}: NOMAD is still processing this entry of upload '
                f'{upload_id}. Export again once it is done.'
            )
        if entry.process_status != ProcessStatus.SUCCESS:
            raise SnapshotError(
                f'{mainfile}: NOMAD could not process this entry of upload '
                f'{upload_id} ({entry.process_status}). Fix it, then export again.'
            )
        files = self._upload(upload_id).upload_files
        try:
            with files.read_archive(entry.entry_id) as archive:
                data = archive[entry.entry_id].get('data')
                return None if data is None else to_json(data)
        except KeyError as error:
            # read_archive and the lookup raise it where there is no archive.
            raise SnapshotError(
                f'{mainfile}: NOMAD stored no archive for this entry of upload '
                f'{upload_id}. Process the upload again, then export again.'
            ) from error
        finally:
            files.close()
