"""Comparing and copying references between entries, used by the logbooks."""

from __future__ import annotations

import re
from urllib.parse import unquote

from nomad.metainfo import Reference
from nomad.metainfo.metainfo import MetainfoReferenceError
from nomad.utils import generate_entry_id

__all__ = [
    'absolute_reference',
    'copy_section',
    'reference_key',
    'reference_text',
    'upload_id_of',
]

# '../uploads/<upload>/archive/mainfile/<file>#data', or '../upload/...' for
# the upload of the entry itself.
_MAINFILE = re.compile(
    r'(?:\.\./)?uploads?/(?:(?P<upload>[^/]+)/)?archive/mainfile/(?P<mainfile>[^#]+)'
    r'#/?(?P<path>.*)$'
)


def reference_key(section, upload_id=None):
    """
    Compare references whether they are resolved sections or proxies, and
    whether they name the entry by its ID or by its file (`upload_id` is the
    upload of a reference to the entry's own upload).
    """
    url = getattr(section, 'm_proxy_value', None)
    if isinstance(url, str):
        match = _MAINFILE.search(url)
        upload = match and (match.group('upload') or upload_id)
        if upload:
            entry_id = generate_entry_id(upload, unquote(match.group('mainfile')))
            return entry_id, match.group('path') or 'data'
        match = re.search(r'archive/([^#/]+)#/?(.*)$', url)
        if match:
            return match.group(1), match.group(2) or 'data'
        return url
    return id(section)


def upload_id_of(archive) -> str | None:
    """The upload of the entry being normalized, if known."""
    metadata = getattr(archive, 'metadata', None)
    return getattr(metadata, 'upload_id', None) or None


def reference_text(reference) -> str:
    """How to name a reference in a message: its URL, or the section."""
    url = getattr(reference, 'm_proxy_value', None)
    return url if isinstance(url, str) else str(reference)


def absolute_reference(value):
    """
    References to entries in the same upload are stored as '../upload/...', which
    would point into the wrong upload once copied to a logbook in another upload.
    Rewrite them as '../uploads/<upload_id>/...'; other values are kept as they are.
    """
    url = getattr(value, 'm_proxy_value', None)
    if isinstance(url, str) and not url.startswith('../upload/'):
        return value
    try:
        resolved = value.m_proxy_resolve() if isinstance(url, str) else value
        metadata = resolved.m_root().metadata
    except (AttributeError, MetainfoReferenceError):
        return value
    if metadata is None or not metadata.upload_id or not metadata.entry_id:
        return value
    return (
        f'../uploads/{metadata.upload_id}/archive/{metadata.entry_id}'
        f'#{resolved.m_path()}'
    )


def copy_section(section, exclude=frozenset()):
    """
    Copy a section with its sub-sections; references are kept, not copied.
    Quantities named in `exclude` are left out, in the sub-sections too.
    """
    copied = section.m_def.section_cls()
    for quantity in section.m_def.all_quantities.values():
        if quantity.name in exclude:
            continue
        if section.m_is_set(quantity):
            value = section.m_get(quantity)
            if isinstance(quantity.type, Reference):
                value = absolute_reference(value)
            copied.m_set(quantity, value)
    for sub_section in section.m_def.all_sub_sections.values():
        for child in section.m_get_sub_sections(sub_section):
            copied.m_add_sub_section(sub_section, copy_section(child, exclude))
    return copied
