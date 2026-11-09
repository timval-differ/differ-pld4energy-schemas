"""
The Sample entries the logbook normalizer writes into the upload for samples
made in a run that the entry editor (not the dashboard) recorded.
"""

import json

from helpers.database import database_uploads
from helpers.nomad_harness import UPLOAD_ID, assert_no_errors, process_file
from nomad.datamodel import EntryArchive, EntryMetadata
from nomad.utils import generate_entry_id
from nomad_material_processing.utils import get_reference
from structlog.testing import CapturingLogger

from differ_pld4e_schemas.pld_deposition import SAPLDLogbook
from differ_pld4e_schemas.sample import SampleInRun

LOGBOOK = 'run.archive.json'
SAMPLE_ID = 'SA-PLD_2026-10-22_09:00_S01'
SAMPLE_FILE = 'SA-PLD_2026-10-22_09_00_S01.archive.json'
SUBSTRATE = '../uploads/target_db/archive/substrate_si#/data'


def _write_logbook(directory, **sample):
    logbook = SAPLDLogbook(
        datetime='2026-10-22T09:00:00+02:00',
        samples=[SampleInRun(origin='New sample', substrate=SUBSTRATE, **sample)],
    )
    (directory / LOGBOOK).write_text(
        json.dumps({'data': logbook.m_to_dict(with_root_def=True)}), encoding='utf-8'
    )


def _process(directory):
    return process_file(directory, LOGBOOK, other_uploads=database_uploads())


def test_new_sample_gets_a_sample_entry(tmp_path):
    _write_logbook(tmp_path)
    archive, logs, upload = _process(tmp_path)
    assert_no_errors(logs)
    assert upload.created == [SAMPLE_FILE]
    data = json.loads((tmp_path / SAMPLE_FILE).read_text(encoding='utf-8'))['data']
    assert data['m_def'].endswith('.Sample')
    assert data['sample_id'] == SAMPLE_ID
    (item,) = archive.data.samples
    entry_id = generate_entry_id(UPLOAD_ID, SAMPLE_FILE)
    # NOMAD stores the fragment as '#/data'; the entry is what matters.
    entry = get_reference(UPLOAD_ID, entry_id).split('#')[0]
    assert item.reference.m_proxy_value.split('#')[0] == entry
    assert item.lab_id == SAMPLE_ID


def test_existing_sample_file_is_not_overwritten(tmp_path):
    _write_logbook(tmp_path)
    _process(tmp_path)
    before = (tmp_path / SAMPLE_FILE).read_bytes()
    _, logs, upload = _process(tmp_path)
    assert_no_errors(logs)
    assert upload.created == []
    assert (tmp_path / SAMPLE_FILE).read_bytes() == before


def test_no_sample_entry_without_an_upload():
    logbook = SAPLDLogbook(
        datetime='2026-10-22T09:00:00+02:00',
        samples=[SampleInRun(origin='New sample', substrate=SUBSTRATE)],
    )
    logbook.normalize(
        EntryArchive(data=logbook, metadata=EntryMetadata()), CapturingLogger()
    )
    (item,) = logbook.samples
    assert item.sample_id == SAMPLE_ID
    assert item.reference is None
    assert item.lab_id is None
