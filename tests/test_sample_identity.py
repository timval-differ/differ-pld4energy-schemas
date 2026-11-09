"""
A sample's identity: its ID (never given twice in a run), its UUID (the same
however often it is processed) and its Sample entry (only linked by the
logbook that made it).
"""

import json

from helpers import ENTRY_CREATE_TIME
from helpers import pld_forms as pld
from helpers.database import database_uploads
from helpers.nomad_harness import assert_no_errors, errors, process_file, warnings
from nomad.datamodel import EntryArchive, EntryMetadata
from structlog.testing import CapturingLogger

from differ_pld4e_schemas.dashboards.pld_logbook.rules import compute, validate
from differ_pld4e_schemas.pld_deposition import SAPLDLogbook
from differ_pld4e_schemas.sample import (
    Sample,
    SampleInRun,
    assign_sample_numbers,
    number_of,
    sample_uuid_for,
)

SUBSTRATE = '../uploads/target_db/archive/substrate_si#/data'
START = '2026-10-22T09:00:00+02:00'
LOGBOOK = 'run.archive.json'
OTHER_LOGBOOK = 'other.archive.json'
S01 = 'SA-PLD_2026-10-22_09:00_S01'
S01_FILE = 'SA-PLD_2026-10-22_09_00_S01.archive.json'


def _new(**kwargs):
    return SampleInRun(origin='New sample', substrate=SUBSTRATE, **kwargs)


def _normalize(logbook, created=ENTRY_CREATE_TIME):
    logger = CapturingLogger()
    archive = EntryArchive(
        data=logbook, metadata=EntryMetadata(entry_create_time=created)
    )
    logbook.normalize(archive, logger)
    return [(call[0], call[1][0]) for call in logger.calls]


def _write(directory, name, data):
    (directory / name).write_text(json.dumps({'data': data}), encoding='utf-8')


def _write_logbook(directory, *samples, name=LOGBOOK):
    logbook = SAPLDLogbook(datetime=START, samples=list(samples))
    _write(directory, name, logbook.m_to_dict(with_root_def=True))


def _process(directory, name=LOGBOOK):
    return process_file(directory, name, other_uploads=database_uploads())


# Numbering


def test_numbers_follow_the_highest_stored_number():
    assert number_of('SA-PLD_2026-10-22_09:00_S12') == 12  # noqa: PLR2004
    assert number_of('no number') is None
    rows = [(True, None), (False, 'x_S07'), (True, 'y_S02'), (True, None)]
    # Existing samples (not made here) do not count.
    assert assign_sample_numbers(rows) == [3, None, None, 4]
    assert assign_sample_numbers([(True, None), (True, None)]) == [1, 2]
    assert assign_sample_numbers([]) == []


def test_a_removed_sample_does_not_pass_on_its_number():
    # S01 was removed from the run; S02 is saved; a new sample is added.
    logbook = SAPLDLogbook(
        datetime=START,
        samples=[_new(sample_id='SA-PLD_2026-10-22_09:00_S02'), _new()],
    )
    _normalize(logbook)
    assert [s.sample_id for s in logbook.samples] == [
        'SA-PLD_2026-10-22_09:00_S02',
        'SA-PLD_2026-10-22_09:00_S03',
    ]


def test_dashboard_numbers_after_the_saved_samples():
    data = pld.form()
    saved = {
        **data['samples'][0],
        'uid': 'saved',
        'ref': '../upload/archive/mainfile/LA-PLD_2026-10-22_09_15_S02.archive.json#data',
        'sample_id': 'LA-PLD_2026-10-22_09:15_S02',
    }
    data['samples'] = [saved, data['samples'][0]]
    assert compute('sample_id', data['samples'][1], data) == (
        'LA-PLD_2026-10-22_09:15_S03'
    )
    assert not [e for e in validate(data, pld.SPEC) if 'more than once' in e['message']]


def test_sample_without_origin_is_a_new_sample():
    data = pld.form(samples__0__origin=None)
    assert compute('sample_id', data['samples'][0], data) == (
        'LA-PLD_2026-10-22_09:15_S01'
    )
    files = pld.form_to_files(data, pld.SPEC)['files']
    assert files[0]['kind'] == 'sample'


# Sample IDs on the lab clock


def test_sample_id_and_run_name_are_on_the_lab_clock():
    logbook = SAPLDLogbook(datetime='2026-10-22T07:00:00+00:00', samples=[_new()])
    _normalize(logbook)
    assert logbook.samples[0].sample_id == S01
    assert logbook.name == 'SA-PLD 2026-10-22 09:00'


def test_sample_keeps_an_id_made_in_utc_by_an_earlier_version(tmp_path):
    legacy_file = 'SA-PLD_2026-10-22_07_00_S01.archive.json'
    _write(tmp_path, legacy_file, {'m_def': 'differ_pld4e_schemas.sample.Sample'})
    _write_logbook(tmp_path, _new())
    archive, logs, upload = _process(tmp_path)
    assert archive.data.samples[0].sample_id == 'SA-PLD_2026-10-22_07:00_S01'
    assert upload.created == []
    assert archive.data.samples[0].reference is not None


# A run without a start


def test_run_without_start_takes_the_entry_creation_time():
    first = SAPLDLogbook(samples=[_new()])
    records = _normalize(first)
    again = SAPLDLogbook(samples=[_new()])
    _normalize(again)
    assert first.samples[0].sample_id == S01  # 07:00 UTC is 09:00 on the lab clock
    assert again.samples[0].sample_id == first.samples[0].sample_id
    assert any('creat' in message for level, message in records if level == 'warning')


def test_run_without_any_time_gets_no_sample_ids():
    logbook = SAPLDLogbook(samples=[_new()])
    records = _normalize(logbook, created=None)
    assert logbook.samples[0].sample_id is None
    assert logbook.samples[0].reference is None
    assert any(level == 'error' for level, _ in records)


# UUIDs


def test_sample_uuid_is_the_same_on_every_normalize():
    one, two = SAPLDLogbook(datetime=START, samples=[_new()]), None
    _normalize(one)
    two = SAPLDLogbook(datetime=START, samples=[_new()])
    _normalize(two)
    assert one.samples[0].sample_uuid == two.samples[0].sample_uuid
    assert one.samples[0].sample_uuid == sample_uuid_for(S01)


def test_stored_uuid_is_kept():
    logbook = SAPLDLogbook(datetime=START, samples=[_new(sample_uuid='printed-label')])
    _normalize(logbook)
    assert logbook.samples[0].sample_uuid == 'printed-label'


def test_sample_entry_uuid_follows_its_id():
    sample = Sample(sample_id=S01)
    sample.normalize(
        EntryArchive(data=sample, metadata=EntryMetadata(entry_name='s')),
        CapturingLogger(),
    )
    assert sample.sample_uuid == sample_uuid_for(S01)


def test_existing_sample_takes_the_uuid_of_its_entry(tmp_path):
    logbook = SAPLDLogbook(
        datetime=START,
        samples=[
            SampleInRun(
                origin='Existing sample',
                reference='../uploads/u0/archive/sample0#/data',
                sample_uuid='random-from-an-old-dashboard',
            )
        ],
    )
    _write(tmp_path, LOGBOOK, logbook.m_to_dict(with_root_def=True))
    archive, logs, _ = _process(tmp_path)
    assert_no_errors(logs)
    (item,) = archive.data.samples
    assert item.sample_uuid == sample_uuid_for('LA-PLD_2026-01-05_10:00_S01')


def test_dashboard_uuid_is_derived_and_existing_samples_get_none():
    data = pld.form()
    data['samples'].append(
        {'uid': 'old', 'origin': 'Existing sample', 'sample': pld.EXISTING}
    )
    one = pld._logbook(data)['samples']
    two = pld._logbook(data)['samples']
    assert one[0]['sample_uuid'] == two[0]['sample_uuid']
    assert one[0]['sample_uuid'] == sample_uuid_for(one[0]['sample_id'])
    assert 'sample_uuid' not in one[1]


# The Sample entry belongs to the logbook that made it


def test_dashboard_sample_entry_records_its_logbook():
    result = pld.form_to_files(pld.FORM, pld.SPEC)
    sample = result['files'][0]['archive']['data']
    assert sample['made_in'] == result['logbook_file']


def test_new_sample_entry_records_its_logbook(tmp_path):
    _write_logbook(tmp_path, _new())
    _, logs, upload = _process(tmp_path)
    assert_no_errors(logs)
    assert upload.created == [S01_FILE]
    data = json.loads((tmp_path / S01_FILE).read_text(encoding='utf-8'))['data']
    assert data['made_in'] == LOGBOOK


def test_sample_entry_of_another_logbook_is_not_linked(tmp_path):
    _write(tmp_path, S01_FILE, {'m_def': 'x.Sample', 'made_in': OTHER_LOGBOOK})
    _write_logbook(tmp_path, _new())
    archive, logs, upload = _process(tmp_path)
    assert archive.data.samples[0].reference is None
    assert upload.created == []
    assert any(OTHER_LOGBOOK in log['event'] for log in errors(logs))


def test_own_sample_entry_is_linked_again(tmp_path):
    _write_logbook(tmp_path, _new())
    _process(tmp_path)
    archive, logs, upload = _process(tmp_path)
    assert_no_errors(logs)
    assert archive.data.samples[0].reference is not None


def test_sample_entry_without_its_logbook_is_linked_with_a_warning(tmp_path):
    _write(tmp_path, S01_FILE, {'m_def': 'x.Sample'})
    _write_logbook(tmp_path, _new())
    archive, logs, _ = _process(tmp_path)
    assert archive.data.samples[0].reference is not None
    assert any('does not record the logbook' in w for w in warnings(logs))
