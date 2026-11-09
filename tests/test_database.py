"""
Targets and substrate types live in one upload, the target and substrate
database, which only maintainers can edit (see `differ_pld4e_schemas.database`).
"""

import pytest
from helpers import DATABASE_UPLOAD
from nomad.datamodel import EntryArchive, EntryMetadata
from structlog.testing import CapturingLogger

from differ_pld4e_schemas.dashboards.pld_logbook.rules import validate
from differ_pld4e_schemas.dashboards.pld_logbook.spec import form_spec
from differ_pld4e_schemas.database import (
    database_reference_error,
    reference_upload_id,
)
from differ_pld4e_schemas.pld_deposition import SAPLDLogbook, SelectedTarget
from differ_pld4e_schemas.sample import Sample, SubstrateType
from differ_pld4e_schemas.target import PLDTarget, SputterTarget

OTHER_UPLOAD = 'someones_upload'


def _in_upload(section, upload_id):
    """Normalize `section` as the data of an entry in `upload_id`."""
    archive = EntryArchive(data=section, metadata=EntryMetadata(upload_id=upload_id))
    logger = CapturingLogger()
    section.normalize(archive, logger)
    return [(call.method_name, call.args[0]) for call in logger.calls]


def _database_problems(calls):
    return [call for call in calls if 'target and substrate database' in call[1]]


@pytest.mark.parametrize(
    'entry',
    [
        lambda: PLDTarget(material='8YSZ', radius=0.0125),
        lambda: SputterTarget(material='Ta', diameter=0.0508),
        lambda: SubstrateType(material='SrTiO3', size='10x10 mm'),
    ],
)
def test_targets_and_substrates_belong_in_the_database(entry):
    assert _database_problems(_in_upload(entry(), DATABASE_UPLOAD)) == []
    problems = _database_problems(_in_upload(entry(), OTHER_UPLOAD))
    assert [level for level, _ in problems] == ['error']
    assert DATABASE_UPLOAD in problems[0][1]


def _substrate_in(upload_id):
    substrate = SubstrateType(material='SrTiO3')
    EntryArchive(data=substrate, metadata=EntryMetadata(upload_id=upload_id))
    return substrate


def test_sample_substrate_comes_from_the_database():
    sample = Sample(substrate=_substrate_in(DATABASE_UPLOAD))
    assert _database_problems(_in_upload(sample, OTHER_UPLOAD)) == []
    sample = Sample(substrate=_substrate_in(OTHER_UPLOAD))
    problems = _database_problems(_in_upload(sample, OTHER_UPLOAD))
    assert [level for level, _ in problems] == ['warning']


def test_logbook_targets_come_from_the_database():
    def logbook_with_target_in(upload_id):
        target = PLDTarget(material='8YSZ', radius=0.0125)
        EntryArchive(data=target, metadata=EntryMetadata(upload_id=upload_id))
        return SAPLDLogbook(targets=[SelectedTarget(target=target, target_number=1)])

    calls = _in_upload(logbook_with_target_in(DATABASE_UPLOAD), OTHER_UPLOAD)
    assert _database_problems(calls) == []
    calls = _in_upload(logbook_with_target_in(OTHER_UPLOAD), OTHER_UPLOAD)
    assert [level for level, _ in _database_problems(calls)] == ['warning']


def test_reference_upload_of_a_url():
    class Proxy:
        def __init__(self, url):
            self.m_proxy_value = url

    archive = EntryArchive(metadata=EntryMetadata(upload_id='own'))
    assert reference_upload_id(Proxy('../uploads/abc/archive/e1#/data')) == 'abc'
    assert reference_upload_id(Proxy('../upload/archive/e1#/data'), archive) == 'own'


def test_dashboard_reference_must_be_in_the_database():
    reference = f'../uploads/{DATABASE_UPLOAD}/archive/t1#/data'
    assert database_reference_error(reference, DATABASE_UPLOAD) is None
    assert database_reference_error(
        f'../uploads/{OTHER_UPLOAD}/archive/t1#/data', DATABASE_UPLOAD
    ) == ('Choose one from the target and substrate database.')
    # Without a database nothing can be chosen.
    assert 'not set up' in database_reference_error(reference, None)


def test_dashboard_spec_names_the_database():
    spec = form_spec()
    assert spec['database_upload_id'] == DATABASE_UPLOAD
    samples = next(s for s in spec['sections'] if s['key'] == 'samples')
    targets = next(s for s in spec['sections'] if s['key'] == 'targets')
    substrate = next(f for f in samples['fields'] if f['key'] == 'substrate')
    target = next(f for f in targets['fields'] if f['key'] == 'target')
    assert substrate['database'] is True
    assert target['database'] is True


def test_dashboard_rejects_targets_and_substrates_from_elsewhere():
    from helpers.pld_forms import FORM, form, messages

    spec = form_spec()
    assert validate(FORM, spec) == []
    elsewhere = f'../uploads/{OTHER_UPLOAD}/archive/x#/data'
    errors = messages(
        validate(
            form(samples__0__substrate=elsewhere, targets__0__target=elsewhere), spec
        )
    )
    expected = 'Choose one from the target and substrate database.'
    assert errors['samples.0.substrate'] == expected
    assert errors['targets.0.target'] == expected
