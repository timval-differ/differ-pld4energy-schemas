"""
The uploads of this NOMAD, read on the server as one user (see
`differ_pld4e_schemas.snapshot.Source`).

Every upload is checked with NOMAD's own rule for reading an upload before
anything of it is read: the export must not hand out files of an upload the
user cannot see, such as another researcher's referenced sample. The files are
then read as NOMAD's raw-file API reads them (`upload.upload_files`).
"""

from __future__ import annotations

from fastapi import HTTPException

from differ_pld4e_schemas.snapshot import SnapshotError


def readable_upload(upload_id: str, user):
    """The upload, if `user` may read it; else SnapshotError."""
    from nomad.app.v1.routers.uploads.utils import get_upload_with_read_access

    try:
        return get_upload_with_read_access(upload_id, user, include_others=True)
    except HTTPException as error:
        raise SnapshotError(
            f'Cannot read upload {upload_id}: {error.detail}'
        ) from error


class NomadFilesSource:
    def __init__(self, user):
        self.user = user
        self._uploads: dict = {}

    def _files(self, upload_id: str):
        if upload_id not in self._uploads:
            self._uploads[upload_id] = readable_upload(upload_id, self.user)
        return self._uploads[upload_id].upload_files

    def raw_files(self, upload_id: str) -> dict[str, bytes]:
        files = self._files(upload_id)
        try:
            result = {}
            for info in files.raw_listdir(recursive=True, files_only=True):
                with files.raw_file(info.path, 'rb') as file:
                    result[info.path] = file.read()
            return result
        finally:
            files.close()

    def raw_file(self, upload_id: str, path: str) -> bytes:
        files = self._files(upload_id)
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
        from nomad.processing import Entry

        if upload_id not in self._uploads:  # the access check
            self._uploads[upload_id] = readable_upload(upload_id, self.user)
        # An entry made from part of a file cannot be named by its file.
        return {
            entry.entry_id: entry.mainfile
            for entry in Entry.objects(upload_id=upload_id).only(
                'entry_id', 'mainfile', 'mainfile_key'
            )
            if not entry.mainfile_key
        }
