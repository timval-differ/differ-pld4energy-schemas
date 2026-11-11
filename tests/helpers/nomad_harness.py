"""
Process entries the way a NOMAD server does, without mongo or Elasticsearch.

`LocalUpload` is a metainfo context for one upload kept in a directory. It
resolves references to entries of this upload (by entry ID or mainfile) by
parsing the raw files, and references to other uploads from archive dicts
given to it. Files written while normalizing (Sample entries) land in the
directory and are recorded in `created`.

`process_file` parses a mainfile with NOMAD's archive parser and runs the whole
normalizer chain (`nomad.client.normalize_all`), collecting what is logged.
"""

import logging
import re
from pathlib import Path

from nomad.client import normalize_all
from nomad.datamodel import EntryArchive, EntryMetadata
from nomad.datamodel.context import Context
from nomad.metainfo import MetainfoReferenceError
from nomad.parsing.parser import ArchiveParser
from nomad.utils import generate_entry_id
from structlog.testing import capture_logs

UPLOAD_ID = 'test_upload'
ERROR_LEVELS = {'error', 'critical', 'exception'}


class LocalUpload(Context):
    def __init__(self, directory, upload_id=UPLOAD_ID, other_uploads=None):
        super().__init__()
        self.directory = Path(directory)
        self._upload_id = upload_id
        # {upload_id: {entry_id: archive dict}}
        self.other_uploads = other_uploads or {}
        self.created: list[str] = []

    @property
    def upload_id(self):
        return self._upload_id

    def raw_path(self):
        return str(self.directory)

    def raw_file(self, path, mode='r', *args, **kwargs):
        if 'b' not in mode:
            # As on a NOMAD server (Linux): text is UTF-8.
            kwargs.setdefault('encoding', 'utf-8')
        return (self.directory / path).open(mode, *args, **kwargs)

    def raw_path_exists(self, path):
        return (self.directory / path).exists()

    def process_updated_raw_file(self, path, allow_modify=False):
        self.created.append(path)

    def get_reference(self, mainfile):
        entry_id = generate_entry_id(self.upload_id, mainfile)
        return f'../uploads/{self.upload_id}/archive/{entry_id}'

    def _mainfile_of(self, entry_id):
        for path in self.directory.rglob('*'):
            mainfile = path.relative_to(self.directory).as_posix()
            if generate_entry_id(self.upload_id, mainfile) == entry_id:
                return mainfile
        return None

    def load_archive(self, entry_id, upload_id, installation_url):
        if upload_id in (None, self.upload_id):
            mainfile = self._mainfile_of(entry_id)
            if mainfile is None:
                raise MetainfoReferenceError(f'Could not load {entry_id}.')
            return self.load_raw_file(mainfile, self.upload_id, installation_url)
        try:
            data = self.other_uploads[upload_id][entry_id]
        except KeyError:
            raise MetainfoReferenceError(
                f'Could not load {entry_id} of upload {upload_id}.'
            ) from None
        context = LocalUpload(self.directory, upload_id, self.other_uploads)
        archive = EntryArchive.m_from_dict(data, m_context=context)
        archive.metadata = EntryMetadata(upload_id=upload_id, entry_id=entry_id)
        return archive

    def load_raw_file(self, path, upload_id, installation_url, url=None):
        if upload_id not in (None, self.upload_id):
            raise MetainfoReferenceError(f'Could not load {path} of {upload_id}.')
        return parse_file(self, path)


def parse_file(context, mainfile):
    archive = EntryArchive(
        m_context=context,
        metadata=EntryMetadata(
            upload_id=context.upload_id,
            mainfile=mainfile,
            entry_id=generate_entry_id(context.upload_id, mainfile),
        ),
    )
    with context.raw_file(mainfile) as file:
        ArchiveParser().parse_file(mainfile, file, archive)
    return archive


# What nomad.utils.ClassicLogger appends to an event: the bound values, as
# ' (normalizer=MetainfoNormalizer, ...)', or ' ()' when there are none.
_BOUND_VALUES = re.compile(r' \((?:[\w.]+=[^,()]*(?:, [\w.]+=[^,()]*)*)?\)$')


def event_of(record) -> str:
    """The event of a log record, without the values NOMAD's logger binds."""
    return _BOUND_VALUES.sub('', record.getMessage())


class _LogRecords(logging.Handler):
    """
    NOMAD logs with the standard logging module when installed without its
    infrastructure extras (as in CI), through nomad.utils.ClassicLogger, which
    appends the bound values to the event; both kinds are collected, as events.
    """

    def __init__(self):
        super().__init__(logging.DEBUG)
        self.logs = []

    def emit(self, record):
        self.logs.append(
            {'log_level': record.levelname.lower(), 'event': event_of(record)}
        )


def process_file(directory, mainfile, *, upload_id=UPLOAD_ID, other_uploads=None):
    """
    Parse `mainfile` (relative to `directory`) and run all normalizers.
    Returns (archive, logs, context); logs are dicts with 'log_level' and
    'event'.
    """
    context = LocalUpload(directory, upload_id, other_uploads)
    records = _LogRecords()
    root = logging.getLogger()
    root.addHandler(records)
    try:
        with capture_logs() as logs:
            archive = parse_file(context, mainfile)
            normalize_all(archive)
    finally:
        root.removeHandler(records)
    return archive, list(logs) + records.logs, context


def errors(logs):
    return [log for log in logs if log.get('log_level') in ERROR_LEVELS]


def warnings(logs):
    return [log['event'] for log in logs if log.get('log_level') == 'warning']


def assert_no_errors(logs):
    found = errors(logs)
    assert not found, '\n'.join(
        f'{log["event"]}: {log.get("exc_info") or log.get("exception") or ""}'
        for log in found
    )


def process_copy(source, directory, **kwargs):
    """Process a copy of the file `source` as the mainfile of an upload kept
    in `directory`, so that files written while processing land there."""
    source = Path(source)
    (Path(directory) / source.name).write_bytes(source.read_bytes())
    return process_file(directory, source.name, **kwargs)
