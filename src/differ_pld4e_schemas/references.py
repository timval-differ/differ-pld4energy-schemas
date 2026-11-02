"""Comparing and copying references between entries, used by the logbooks."""

from __future__ import annotations

import re

from nomad.metainfo import Reference
from nomad.metainfo.metainfo import MetainfoReferenceError

__all__ = ['absolute_reference', 'copy_section', 'reference_key']


def reference_key(section):
    """Compare references whether they are resolved sections or proxies."""
    url = getattr(section, 'm_proxy_value', None)
    if isinstance(url, str):
        match = re.search(r'archive/([^#/]+)#/?(.*)$', url)
        if match:
            return match.group(1), match.group(2) or 'data'
        return url
    return id(section)


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


def copy_section(section):
    """Copy a section with its sub-sections; references are kept, not copied."""
    copied = section.m_def.section_cls()
    for quantity in section.m_def.all_quantities.values():
        if section.m_is_set(quantity):
            value = section.m_get(quantity)
            if isinstance(quantity.type, Reference):
                value = absolute_reference(value)
            copied.m_set(quantity, value)
    for sub_section in section.m_def.all_sub_sections.values():
        for child in section.m_get_sub_sections(sub_section):
            copied.m_add_sub_section(sub_section, copy_section(child))
    return copied
