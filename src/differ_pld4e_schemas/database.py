"""
The target and substrate database: one NOMAD upload that holds every target
and substrate type of the lab.

Only maintainers create, edit and delete targets and substrate types. NOMAD
grants that per upload, so the database is a single upload in which the
maintainers are coauthors (they can edit it) and everyone else is a reviewer
(they can only view it). Logbooks and samples choose their targets and
substrates from that upload; an external sample on a substrate that is not in
the database describes it in `substrate_details` instead.

The upload is configured in nomad.yaml::

    plugins:
      entry_points:
        options:
          differ_pld4e_schemas.schema_packages:schema_package_entry_point:
            database_upload_id: <upload id>
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

from nomad.metainfo.metainfo import MetainfoReferenceError

if TYPE_CHECKING:
    from nomad.datamodel.datamodel import EntryArchive
    from structlog.stdlib import BoundLogger

__all__ = [
    'ENTRY_POINT_ID',
    'check_database_entry',
    'check_database_reference',
    'database_reference_error',
    'database_upload_id',
    'reference_upload_id',
    'url_upload_id',
]

ENTRY_POINT_ID = 'differ_pld4e_schemas.schema_packages:schema_package_entry_point'


def database_upload_id() -> str | None:
    """The upload of the target and substrate database, None if not set up."""
    try:
        from nomad.config import config

        entry_point = config.get_plugin_entry_point(ENTRY_POINT_ID)
    except (AttributeError, KeyError, ImportError):  # plugins not loaded
        return None
    return getattr(entry_point, 'database_upload_id', None) or None


def url_upload_id(url: str) -> str | None:
    """The upload of a reference written as '../uploads/<upload id>/...'."""
    match = re.match(r'(?:\.\./)?uploads/([^/]+)/', url or '')
    return match.group(1) if match else None


def database_reference_error(reference: str, database: str | None) -> str | None:
    """
    Why a reference chosen in a logbook dashboard is not from the database, or
    None if it is.
    """
    if not database:
        return (
            'The target and substrate database is not set up in NOMAD yet. Ask '
            'a maintainer.'
        )
    if url_upload_id(reference) != database:
        return 'Choose one from the target and substrate database.'
    return None


def _own_upload_id(archive: EntryArchive | None) -> str | None:
    metadata = getattr(archive, 'metadata', None)
    return getattr(metadata, 'upload_id', None) or None


def reference_upload_id(reference, archive: EntryArchive | None = None) -> str | None:
    """
    The upload a reference points into, whether it is a proxy or a resolved
    section; None if that cannot be told. A reference into the same upload
    ('../upload/...') is in the upload of `archive`.
    """
    if reference is None:
        return None
    url = getattr(reference, 'm_proxy_value', None)
    if isinstance(url, str):
        upload = url_upload_id(url)
        if upload:
            return upload
        if url.startswith(('../upload/', '#', '/')):
            return _own_upload_id(archive)
    try:
        metadata = reference.m_root().metadata
    except (AttributeError, MetainfoReferenceError):
        return None
    return getattr(metadata, 'upload_id', None) or None


def check_database_entry(
    archive: EntryArchive | None, logger: BoundLogger, noun: str
) -> None:
    """Report a target or substrate type that is made outside the database."""
    database = database_upload_id()
    upload = _own_upload_id(archive)
    if database and upload and upload != database:
        logger.error(
            f'This {noun} is not in the target and substrate database '
            f'(upload {database}), so logbooks cannot select it. Only maintainers '
            f'add {noun}s, in that upload.'
        )


def check_database_reference(
    reference, archive: EntryArchive | None, logger: BoundLogger, noun: str
) -> None:
    """Report a target or substrate chosen from outside the database."""
    database = database_upload_id()
    if not database or reference is None:
        return
    upload = reference_upload_id(reference, archive)
    if upload and upload != database:
        logger.warning(
            f'The {noun} is not from the target and substrate database '
            f'(upload {database}). Choose one from the database.'
        )
