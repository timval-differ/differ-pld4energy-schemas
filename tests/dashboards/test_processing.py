"""
The files the dashboards write, processed as NOMAD processes an upload: parsed
by the archive parser and run through all normalizers, with the references to
the database and to other samples resolved.
"""

import copy
import json

import pytest
from helpers import pld_forms as pld
from helpers import sputter_forms as sputter
from helpers.database import database_uploads
from helpers.nomad_harness import assert_no_errors, process_file, warnings

from differ_pld4e_schemas.sample import Sample


def _with_existing_sample():
    data = copy.deepcopy(pld.FORM)
    data['samples'].append(
        {'uid': 'old', 'origin': 'Existing sample', 'sample': pld.EXISTING}
    )
    return data


FORMS = {
    'LA-PLD': (pld, pld.FORM),
    'SA-PLD': (pld, pld.sa_form()),
    'SA-PLD annealing only': (pld, pld.annealing_form()),
    'LA-PLD with an existing sample': (pld, _with_existing_sample()),
    'SPS': (sputter, sputter.FORM),
}


def _write(directory, module, data):
    result = module.form_to_files(data, module.SPEC)
    assert not result.get('errors'), result.get('errors')
    for file in result['files']:
        (directory / file['file_name']).write_text(
            json.dumps(file['archive']), encoding='utf-8'
        )
    return result


@pytest.mark.parametrize('name', FORMS)
def test_dashboard_files_process_without_errors(tmp_path, name):
    module, data = FORMS[name]
    result = _write(tmp_path, module, data)
    archive, logs, context = process_file(
        tmp_path, result['logbook_file'], other_uploads=database_uploads()
    )
    assert_no_errors(logs)
    assert warnings(logs) == []
    assert archive.metadata.entry_type == type(archive.data).__name__
    # The dashboard writes the Sample files itself; the normalizer adds none.
    assert context.created == []

    made_here = [f for f in result['files'] if f['kind'] == 'sample']
    for file in made_here:
        sample_archive, sample_logs, _ = process_file(
            tmp_path, file['file_name'], other_uploads=database_uploads()
        )
        assert_no_errors(sample_logs)
        assert isinstance(sample_archive.data, Sample)

    for item in archive.data.samples:
        assert item.reference is not None, item.sample_id
        sample = item.reference
        if hasattr(sample, 'm_proxy_resolve'):  # not resolved by a normalizer
            sample = sample.m_proxy_resolve()
        assert isinstance(sample, Sample)
        assert sample.sample_id == item.sample_id


def test_harness_reports_normalizer_errors(tmp_path, monkeypatch):
    """A negative control: an exception in a normalizer is reported."""
    from differ_pld4e_schemas.pld_deposition import LAPLDLogbook

    def broken(self, archive, logger):
        raise ValueError('broken on purpose')

    monkeypatch.setattr(LAPLDLogbook, 'normalize', broken)
    result = _write(tmp_path, pld, pld.FORM)
    _, logs, _ = process_file(
        tmp_path, result['logbook_file'], other_uploads=database_uploads()
    )
    with pytest.raises(AssertionError, match='could not normalize section'):
        assert_no_errors(logs)
