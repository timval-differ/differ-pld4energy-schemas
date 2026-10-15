import os.path

import yaml
from nomad.datamodel import EntryArchive


def test_schema_package():
    test_file = os.path.join('tests', 'data', 'example_deposition.yaml')
    with open(test_file) as archive_file:
        entry_archive = EntryArchive.m_from_dict(yaml.safe_load(archive_file))
    assert entry_archive.data.name == 'Multilayer Ti/Pt deposition'
    assert [step.name for step in entry_archive.data.steps] == [
        'Ti adhesion layer',
        'Pt electrode',
    ]
    assert entry_archive.data.steps[0].deposited_layer.material == 'Ti'
