"""
A self-contained snapshot of an upload, for publication.

In the Oasis, logbooks and samples refer to targets and substrate types in the
target and substrate database, another upload. Published elsewhere, those
references would point at entries that are not there. A snapshot is a copy of
the upload that also holds every entry it refers to in other uploads, with all
references rewritten to stay inside the snapshot.

Upload and entry IDs differ in every NOMAD, so references are rewritten to name
the entry by its file: '../upload/archive/mainfile/<file>#<path>'. Entries from
other uploads are placed in 'referenced/<upload id>/<file>'.

Each archive holds the data NOMAD stored for its entry when processing it, not
only what was saved in the file: what normalizers filled in (a spectrum read
from its file, a plot) is kept as values, because the NOMAD the snapshot is
published on need not run the plugins that made it.

For the same reason the snapshot holds the schemas of its entries as YAML
schemas, one file per plugin (see `yaml_schema`), and entries name their
sections in them: '../upload/raw/schema/<plugin>.archive.yaml#<section>'.

This module has no network code; `build_snapshot` reads through a `Source`.
"""

from __future__ import annotations

import json
import re
from typing import Protocol
from urllib.parse import unquote

import yaml
from nomad.metainfo import Package, Section

from differ_pld4e_schemas.yaml_schema import SCHEMA_DIRECTORY, section_of, yaml_schemas

__all__ = [
    'REFERENCED_DIRECTORY',
    'SCHEMA_DIRECTORY',
    'SnapshotError',
    'Source',
    'build_snapshot',
]

REFERENCED_DIRECTORY = 'referenced'

# Files in which references are rewritten: archives written as text.
_ARCHIVE_SUFFIXES = ('.archive.json', '.archive.yaml', '.archive.yml')

# A reference to another entry, up to its '#<path>': to the upload of the entry
# itself ('../upload/...') or to a named upload ('../uploads/<id>/...', or the
# same after the API URL of a NOMAD), naming the entry by its ID or its file.
_REFERENCE = re.compile(
    r'(?:\.\./|(?P<installation>https?://[^\s"\'#]+?)/)'
    r'(?:upload|uploads/(?P<upload>[^/\s"\'#]+))/archive/'
    r'(?:mainfile/(?P<mainfile>[^#"\'\n]+)|(?P<entry>[^/#\s"\']+))'
)

# The other references NOMAD reads, which are not rewritten: to an entry by
# '/entries/<id>/...' or '/uploads/<id>/...', and to raw files of an upload.
# The last group is a raw file of the upload of the entry itself.
_UNSUPPORTED = re.compile(
    r'[^\s"\']*(?:/entries/[^/\s"\'#]+/(?:archive|raw)#'
    r'|uploads/[^/\s"\'#]+/(?:archive|raw)/'
    r'|(?P<own_raw>\.\./upload/raw/))[^\s"\']*'
)

# The section of an entry or sub-section named by its Python name: 'm_def: a.b.C',
# as a key of its own (not 'my_m_def') and a whole value (not 'a.b-c.D').
_PYTHON_M_DEF = re.compile(
    r'(?<![\w.])(?P<key>(?P<key_quote>["\']?)m_def(?P=key_quote)\s*:\s*)'
    r'(?P<quote>["\']?)(?P<name>[A-Za-z_]\w*(?:\.\w+)+)(?P=quote)'
    r'(?=\s*(?:[,}\]]|$))',
    re.MULTILINE,
)

# Anything that may be a Python name of a definition. Left after the rewriting,
# the name of a plugin's definition (for example as the base of a section in an
# upload's own YAML schema) would not resolve where the snapshot is published.
# Not after '/': the schema files' names start like Python names.
_PYTHON_NAME = re.compile(r'(?<![\w./])[A-Za-z_]\w*(?:\.\w+)+')

# In a file name, these keep NOMAD from finding the entry by its file.
_UNREFERABLE = ('?', '#', '\\', 'mainfile/')


class SnapshotError(Exception):
    """The snapshot cannot be made complete; the message says what is missing."""


class Source(Protocol):
    """Where the uploads are read from, as the user making the snapshot."""

    def raw_files(self, upload_id: str) -> dict[str, bytes]:
        """Every raw file of the upload, by its path in the upload."""

    def mainfiles(self, upload_id: str) -> dict[str, str]:
        """The file of every entry of the upload, by entry ID."""

    def raw_file(self, upload_id: str, path: str) -> bytes:
        """One raw file of the upload."""

    def processed_data(self, upload_id: str, mainfile: str) -> dict | None:
        """
        The `data` that NOMAD stored for the entry of `mainfile` when it processed
        it, or None if the entry has none. Raises `SnapshotError` if the file is
        not an entry that NOMAD processed successfully.
        """


def _is_archive(path: str) -> bool:
    return path.lower().endswith(_ARCHIVE_SUFFIXES)


def _parse_archive(text: str, is_json: bool) -> dict:
    """The archive in `text`; ValueError if it is not one."""
    try:
        archive = json.loads(text) if is_json else yaml.safe_load(text)
    except yaml.YAMLError as error:
        raise ValueError(str(error)) from error
    if archive is None:
        return {}  # an empty YAML file
    if not isinstance(archive, dict):
        raise ValueError('it is not a mapping of sections.')
    return archive


def _is_nomad(section: Section) -> bool:
    return section.qualified_name().split('.')[0] == 'nomad'


def _without_definition_ids(value):
    """
    `value` without the 'm_def_id's NOMAD stores with processed data: they name
    definitions of this NOMAD, which no other NOMAD has.
    """
    if isinstance(value, dict):
        return {
            key: _without_definition_ids(item)
            for key, item in value.items()
            if key != 'm_def_id'
        }
    if isinstance(value, list):
        return [_without_definition_ids(item) for item in value]
    return value


class _Snapshot:
    def __init__(
        self,
        upload_id: str,
        source: Source,
        api_url: str | None,
    ):
        self.upload_id = upload_id
        self.source = source
        self.api_url = api_url.rstrip('/') if api_url else None
        self.files: dict[str, bytes] = {}
        # The archives, by path in the snapshot: their sections are named in the
        # schemas once all are read.
        self._archives: dict[str, str] = {}
        self.problems: list[str] = []
        self._mainfiles: dict[str, dict[str, str]] = {}
        self._files: dict[str, set[str]] = {}
        # Entries of other uploads still to copy, and those already seen.
        self._pending: list[tuple[str, str]] = []
        self._seen: set[tuple[str, str]] = set()

    def _mainfiles_of(self, upload_id: str) -> dict[str, str]:
        if upload_id not in self._mainfiles:
            try:
                self._mainfiles[upload_id] = self.source.mainfiles(upload_id)
            except SnapshotError as error:
                self.problems.append(str(error))
                self._mainfiles[upload_id] = {}
            self._files[upload_id] = set(self._mainfiles[upload_id].values())
        return self._mainfiles[upload_id]

    def _path_in_snapshot(self, upload_id: str, mainfile: str) -> str:
        if upload_id == self.upload_id:
            return mainfile
        return f'{REFERENCED_DIRECTORY}/{upload_id}/{mainfile}'

    def _target(self, match: re.Match, origin: str, path: str) -> str | None:
        """The file in the snapshot of the entry a reference points at."""
        installation = match.group('installation')
        if installation and installation.rstrip('/') != self.api_url:
            self.problems.append(
                f'{path}: "{match.group(0)}" points at an entry in another NOMAD, '
                f'which cannot be copied.'
            )
            return None
        upload_id = match.group('upload') or origin
        known = self._mainfiles_of(upload_id)
        files = self._files[upload_id]
        mainfile = match.group('mainfile')
        if mainfile is not None:
            # The dashboards have written file names both as they are and encoded.
            if mainfile not in files and unquote(mainfile) in files:
                mainfile = unquote(mainfile)
        else:
            mainfile = known.get(match.group('entry'))
        if mainfile is None or mainfile not in files:
            self.problems.append(
                f'{path}: "{match.group(0)}" points at an entry of upload '
                f'{upload_id} that does not exist or that you cannot see.'
            )
            return None
        if any(text in mainfile for text in _UNREFERABLE):
            self.problems.append(
                f'{path}: "{match.group(0)}" points at the file "{mainfile}"; NOMAD '
                f'cannot refer to a file with "?", "#", "\\" or "mainfile/" in its '
                f'name. Rename it.'
            )
            return None
        if upload_id != self.upload_id and (upload_id, mainfile) not in self._seen:
            self._seen.add((upload_id, mainfile))
            self._pending.append((upload_id, mainfile))
        return self._path_in_snapshot(upload_id, mainfile)

    def _with_processed_data(self, text: str, origin: str, path: str) -> str | None:
        """
        The archive `text` of `path` in upload `origin` with the data NOMAD
        stored for its entry, or None (and a problem) if there is none to take.
        An archive without data, such as a schema, is kept as it is.
        """
        is_json = path.lower().endswith('.json')
        try:
            archive = _parse_archive(text, is_json)
        except ValueError as error:
            self.problems.append(f'{path}: cannot be read as an archive: {error}')
            return None
        try:
            data = self.source.processed_data(origin, path)
        except SnapshotError as error:
            self.problems.append(str(error))
            return None
        if data is None:
            if archive.get('data') is not None:
                self.problems.append(
                    f'{path}: NOMAD stored no data for this entry. Process the '
                    f'upload again, then export again.'
                )
                return None
            return text
        archive['data'] = _without_definition_ids(data)
        # In the format of the file, whose name references use. NOMAD reads JSON
        # with Python's json, which takes NaN and infinity as they are written.
        if is_json:
            return json.dumps(archive, indent=2, ensure_ascii=False) + '\n'
        # Not wrapped: a reference broken over two lines would not be rewritten.
        return yaml.safe_dump(
            archive, sort_keys=False, allow_unicode=True, width=float('inf')
        )

    def _rewrite(self, content: bytes, origin: str, path: str) -> str | None:
        """
        `content` of an archive from upload `origin`, with its processed data and
        its references rewritten, or None if it cannot be read.
        """
        try:
            text = content.decode('utf-8')
        except UnicodeDecodeError:
            self.problems.append(f'{path}: is not UTF-8 text, so cannot be read.')
            return None
        text = self._with_processed_data(text, origin, path)
        if text is None:
            return None

        for match in _UNSUPPORTED.finditer(_REFERENCE.sub('', text)):
            if match.group('own_raw') and origin == self.upload_id:
                continue  # the raw files of the upload are in the snapshot
            self.problems.append(
                f'{path}: "{match.group(0)}" is a kind of reference that the '
                f'export cannot rewrite.'
            )

        def replace(match: re.Match) -> str:
            target = self._target(match, origin, path)
            if target is None:
                return match.group(0)
            return f'../upload/archive/mainfile/{target}'

        return _REFERENCE.sub(replace, text)

    def _add(self, path: str, content: bytes, origin: str) -> None:
        if path.startswith('/') or '\\' in path or '..' in path.split('/'):
            self.problems.append(f'"{path}" of upload {origin}: not a path in a ZIP.')
            return
        if _is_archive(path):
            text = self._rewrite(content, origin, path)
            if text is not None:
                self._archives[self._path_in_snapshot(origin, path)] = text
            return
        self.files[self._path_in_snapshot(origin, path)] = content

    def _sections(self) -> dict[str, Section]:
        """Every section the archives name by Python name, by that name."""
        sections = {}
        for path, text in self._archives.items():
            for match in _PYTHON_M_DEF.finditer(text):
                name = match.group('name')
                if name.split('.')[0] == 'nomad' or name in sections:
                    continue  # NOMAD's own sections are in every NOMAD
                section = section_of(name)
                if section is None:
                    self.problems.append(
                        f'{path}: the section "{name}" is not in a schema of this '
                        f'NOMAD, so the export cannot describe it.'
                    )
                elif not _is_nomad(section) and not isinstance(
                    section.m_parent, Package
                ):
                    self.problems.append(
                        f'{path}: the section "{name}" is an inner section, which '
                        f'the export cannot describe.'
                    )
                else:
                    sections[name] = section
        return sections

    def _name_sections(self) -> None:
        """
        Add the YAML schemas of the sections the archives use, and name the
        sections in them. Runs only once every archive could be read.
        """
        sections = self._sections()
        if self.problems:
            return
        packages = list(
            dict.fromkeys(
                section.m_parent
                for section in sections.values()
                if not _is_nomad(section)
            )
        )
        try:
            schemas = yaml_schemas(packages)
        except ValueError as error:
            self.problems.append(f'The schemas cannot be written as YAML: {error}')
            return

        def section(match: re.Match) -> str:
            name = match.group('name')
            if name not in sections:
                return match.group(0)
            if _is_nomad(sections[name]):
                # NOMAD's own section, named by a plugin module that imports it.
                reference = sections[name].qualified_name()
            else:
                reference = schemas.reference(sections[name])
            # Quoted where it was not: in YAML, ' #' would start a comment.
            quote = match.group('quote') or "'"
            return f'{match.group("key")}{quote}{reference}{quote}'

        for path, archive in self._archives.items():
            text = _PYTHON_M_DEF.sub(section, archive)
            for name in dict.fromkeys(_PYTHON_NAME.findall(text)):
                definition = section_of(name)
                if definition is not None and not _is_nomad(definition):
                    self.problems.append(
                        f'{path}: "{name}" names a definition of a plugin by its '
                        f'Python name outside an m_def, which the export cannot '
                        f'rewrite.'
                    )
            self.files[path] = text.encode('utf-8')
        for path, text in schemas.files.items():
            self.files[path] = text.encode('utf-8')

    def build(self) -> dict[str, bytes]:
        own = self.source.raw_files(self.upload_id)
        for directory, use in (
            (REFERENCED_DIRECTORY, 'entries of other uploads'),
            (SCHEMA_DIRECTORY, 'the schemas'),
        ):
            clashes = [path for path in own if path.startswith(f'{directory}/')]
            if clashes:
                raise SnapshotError(
                    f'The upload has files in "{directory}/", where the snapshot '
                    f'puts {use}: {", ".join(sorted(clashes))}'
                )
        for path, content in own.items():
            self._add(path, content, self.upload_id)
        while self._pending:
            upload_id, mainfile = self._pending.pop()
            try:
                content = self.source.raw_file(upload_id, mainfile)
            except SnapshotError as error:
                self.problems.append(str(error))
                continue
            self._add(mainfile, content, upload_id)
        if not self.problems:
            self._name_sections()
        if self.problems:
            raise SnapshotError('\n'.join(dict.fromkeys(self.problems)))
        return self.files


def build_snapshot(
    upload_id: str,
    source: Source,
    api_url: str | None = None,
) -> dict[str, bytes]:
    """
    The files of a self-contained copy of upload `upload_id`, by path.

    `api_url` is the API of the NOMAD that `source` reads ('.../api/v1'):
    references written with that URL are to entries of this NOMAD.

    Raises `SnapshotError`, naming every problem, if a referenced entry cannot
    be read: a snapshot with references that lead nowhere is not made.
    """
    return _Snapshot(upload_id, source, api_url).build()
