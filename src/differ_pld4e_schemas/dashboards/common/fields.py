"""
Building blocks of a form definition.

Field keys:
    key          key in the form data of the containing section or list item
    label        label shown in the form
    kind         text | textarea | number | integer | select | bool | date |
                 time | reference | target_choice | sample_choice |
                 material_choice | rows | file | computed
    unit         pint unit the user enters the value in (converted to the
                 schema's SI unit when the archive is built)
    unit_label   how the unit is shown, if different from `unit`
    archive      dotted path of the quantity in the archive section, relative to
                 the section the containing object maps to; None if the value is
                 handled by the converter itself
    required     whether the value must be filled in while the field is visible
    visible_if   condition, see `values.evaluate`
    options      choices of a select, or `options_by` for choices that depend on
                 another field
    columns      fields of each row of a `rows` field (a repeating sub-section)
    group        heading the field is shown under
"""

from __future__ import annotations


def field(key, label, kind='text', **kwargs):
    kwargs.setdefault('required', kind not in ('textarea', 'bool', 'computed', 'rows'))
    kwargs.setdefault('archive', key)
    return {'key': key, 'label': label, 'kind': kind, **kwargs}


def number(key, label, unit=None, **kwargs):
    return field(key, label, 'number', unit=unit, **kwargs)


def comments(**kwargs):
    kwargs.setdefault('archive', 'description')
    return field('comments', 'Comments', 'textarea', **kwargs)
