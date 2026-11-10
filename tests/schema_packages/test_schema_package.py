from pathlib import Path

import pytest
import yaml
from nomad.datamodel import EntryArchive

from differ_pld4e_schemas.schema_packages import schema_package_entry_point


def test_schema_package():
    package = schema_package_entry_point.load()
    names = {section.name for section in package.section_definitions}
    assert {'SAPLDLogbook', 'LAPLDLogbook', 'SPSLogbook', 'SputterTarget'} <= names


def test_example_entry_loads():
    test_file = (
        Path(__file__).resolve().parents[1] / 'data' / 'example_sps.archive.yaml'
    )
    with open(test_file) as archive_file:
        entry_archive = EntryArchive.m_from_dict(yaml.safe_load(archive_file))
    assert entry_archive.data.name == 'Ta-Ti multilayer on Si'
    thickness = entry_archive.data.steps[2].film_thickness
    assert thickness.to('nm').magnitude == pytest.approx(50)
