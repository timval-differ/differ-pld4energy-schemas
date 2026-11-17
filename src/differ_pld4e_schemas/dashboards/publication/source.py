"""
The uploads of this NOMAD, read on the server as one user (see
`differ_pld4e_schemas.snapshot.Source`).

Every upload is checked with NOMAD's own rule for reading an upload before
anything of it is read: the export must not hand out files of an upload the
user cannot see, such as another researcher's referenced sample. The files are
then read as NOMAD's raw-file API reads them (`upload.upload_files`).

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
        'entry_id', 'mainfile', 'mainfile_key'
    )


class NomadFilesSource:
    def __init__(self, user, read_access=nomad_read_access, entries=nomad_entries):
        self.user = user
        self.read_access = read_access
        self.entries = entries
        self._uploads: dict = {}

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

    def mainfiles(self, upload_id: str) -> dict[str, str]:
        self._upload(upload_id)  # the access check
        # An entry made from part of a file cannot be named by its file.
        return {
            entry.entry_id: entry.mainfile
            for entry in self.entries(upload_id)
            if not entry.mainfile_key
        }
