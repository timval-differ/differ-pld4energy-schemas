"""Helpers to read the schema in tests."""


def enum_values(section_cls, name):
    """The values of the enumeration quantity `name` of `section_cls`."""
    return set(section_cls.m_def.all_quantities[name].type)
