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

The NOMAD it is published on need not run this plugin, so the snapshot also
holds the plugin's schemas as a YAML schema (see `yaml_schema`), and entries
name their sections in it: '../upload/raw/<schema file>#<section>'.

This module has no network code; `build_snapshot` reads through a `Source`.
"""

from __future__ import annotations

import re
from typing import Protocol
from urllib.parse import unquote

from differ_pld4e_schemas.yaml_schema import SCHEMA_PATH, plugin_yaml_schema

__all__ = [
    'REFERENCED_DIRECTORY',
    'SCHEMA_DIRECTORY',
    'SnapshotError',
    'Source',
    'build_snapshot',
]

REFERENCED_DIRECTORY = 'referenced'
# Where the snapshot puts the YAML schema.
SCHEMA_DIRECTORY = SCHEMA_PATH.split('/')[0]

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

# Python names of definitions that only the Oasis has, for example as the base
# of a section in an upload's own YAML schema. Left after the rewriting, they
# would not resolve where the snapshot is published.
_PLUGIN_NAME = re.compile(
    # Not after '/': the schema's file name starts like a Python name.
    r'(?<![\w./])(?:differ_pld4e_schemas|nomad_material_processing)\.\w+(?:\.\w+)*'
)

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


def _is_archive(path: str) -> bool:
    return path.lower().endswith(_ARCHIVE_SUFFIXES)


class _Snapshot:
    def __init__(
        self,
        upload_id: str,
        source: Source,
        api_url: str | None,
    ):
        self.upload_id = upload_id
        self.source = source
        self.schema = plugin_yaml_schema()
        self.api_url = api_url.rstrip('/') if api_url else None
        self.files: dict[str, bytes] = {}
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

    def _rewrite(self, content: bytes, origin: str, path: str) -> bytes:
        """`content` of an archive from upload `origin`, references rewritten."""
        try:
            text = content.decode('utf-8')
        except UnicodeDecodeError:
            self.problems.append(f'{path}: is not UTF-8 text, so cannot be read.')
            return content

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

        text = _REFERENCE.sub(replace, text)
        # After the references: the schema is named as a raw file of the upload,
        # which the check for unsupported references would report.
        unknown: set[str] = set()
        text = _PYTHON_M_DEF.sub(
            lambda match: self._section(match, path, unknown), text
        )
        for name in dict.fromkeys(_PLUGIN_NAME.findall(text)):
            if name in unknown:
                continue  # reported as an unknown section
            self.problems.append(
                f'{path}: "{name}" names a definition of this plugin by its Python '
                f'name outside an m_def, which the export cannot rewrite.'
            )
        return text.encode('utf-8')

    def _section(self, match: re.Match, path: str, unknown: set[str]) -> str:
        """
        An `m_def` by Python name, rewritten to name the section in the schema.
        Names it cannot rewrite are reported and added to `unknown`.
        """
        name = match.group('name')
        if name.split('.')[0] == 'nomad':
            return match.group(0)  # NOMAD's own sections are in every NOMAD
        section = self.schema.section_name(name)
        if section is None:
            unknown.add(name)
            self.problems.append(
                f'{path}: the section "{name}" is not in the schemas of this '
                f'plugin, so the export cannot describe it.'
            )
            return match.group(0)
        # Quoted where it was not: in YAML, ' #' would start a comment.
        quote = match.group('quote') or "'"
        return (
            f'{match.group("key")}{quote}../upload/raw/{SCHEMA_PATH}#{section}{quote}'
        )

    def _add(self, path: str, content: bytes, origin: str) -> None:
        if path.startswith('/') or '\\' in path or '..' in path.split('/'):
            self.problems.append(f'"{path}" of upload {origin}: not a path in a ZIP.')
            return
        if _is_archive(path):
            content = self._rewrite(content, origin, path)
        self.files[self._path_in_snapshot(origin, path)] = content

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
        if self.problems:
            raise SnapshotError('\n'.join(dict.fromkeys(self.problems)))
        self.files[SCHEMA_PATH] = self.schema.text.encode('utf-8')
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
