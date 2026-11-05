import copy

import pytest
from fastapi.testclient import TestClient
from nomad.datamodel import EntryArchive, EntryMetadata

from differ_pld4e_schemas import sps_deposition
from differ_pld4e_schemas.dashboards import (
    pld_logbook_dashboard_entry_point,
    sputter_logbook_dashboard_entry_point,
)
from differ_pld4e_schemas.dashboards.common.archive import SKIPPED_KINDS, quantity_of
from differ_pld4e_schemas.dashboards.sputter_logbook.convert import (
    archive_to_form,
    draft_path,
    form_to_files,
    recipe_to_form,
)
from differ_pld4e_schemas.dashboards.sputter_logbook.rules import (
    compute,
    validate,
    validate_draft,
)
from differ_pld4e_schemas.dashboards.sputter_logbook.spec import form_spec
from differ_pld4e_schemas.sample import SampleInRun
from differ_pld4e_schemas.sps_deposition import (
    SPSLogbook,
    SPSPreSputteringStep,
    SPSSputteringStep,
    SputterPlasma,
)

SPEC = form_spec()
TA = '../uploads/target_db/archive/ta#/data'
TI = '../uploads/target_db/archive/ti#/data'
SI_WAFER = '../uploads/target_db/archive/substrate_si#/data'
EXISTING = '../uploads/u0/archive/sample0#/data'
HTTP_OK = 200
HTTP_BAD_REQUEST = 400
SAMPLE_FILE = 'SPS_2026-10-22_09_15_S01.archive.json'
LOGBOOK_FILE = 'SPS_2026-10-22_0915_Ta-Ti_multilayer.archive.json'

ARGON = {
    'atmosphere': 'Background gas',
    'gas_Ar': True,
    'gas_Ar_flow_setpoint': 20,
    'gas_Ar_flow_readout': 19.8,
    'valve_position': 40,
    'valve_position_fixed': False,
}
DC_PLASMA = {
    'plasma_type': 'DC',
    'voltage': 380,
    'current': 260,
    'power': 100,
}

PRE_SPUTTERING = {
    'uid': 'step1',
    'type': 'pre_sputtering',
    'start_time': '09:20',
    'end_time': '09:30',
    'target': TA,
    **ARGON,
    'pressure': 5e-3,
    **DC_PLASMA,
    'ramp_up_rate': 10,
    'pre_sputter_time': 10,
}
SPUTTERING = {
    'uid': 'step2',
    'type': 'sputtering',
    'start_time': '10:00',
    'end_time': '10:30',
    'x': 0,
    'y': 0,
    'z': 100,
    'spin': 0,
    'heater_rotation': 10,
    'target': TA,
    **ARGON,
    'pressure': 5e-3,
    **DC_PLASMA,
    'shutter': 'open',
    'sputter_time': 20,
    'ramp_down_rate': 10,
    'film_thickness': 50,
}
SPUTTERING_TI = {
    **SPUTTERING,
    'uid': 'step3',
    'target': TI,
    'plasma_type': 'RF',
    'voltage': None,
    'load_capacitance': 1.2,
    'dc_bias': 150,
    'film_thickness': 10,
}
FORM = {
    'run': {
        'operator_name': 'Ada Lovelace',
        'operator_email': 'ada@example.org',
        'system': 'SPS',
        'date': '2026-10-22',
        'time': '09:15',
        'utc_offset': '+02:00',
        'name': 'Ta-Ti multilayer',
    },
    'samples': [
        {
            'uid': 'sub1',
            'origin': 'New sample',
            'substrate': SI_WAFER,
            'substrate_material': 'Si',
        }
    ],
    'chamber': {
        'substrate_carrier': '4" carrier SPS',
        'mask_used': False,
        'base_pressure': 1e-7,
    },
    'targets': [
        {'uid': 't1', 'target': TA, 'material': 'Ta', 'target_number': '1'},
        {'uid': 't2', 'target': TI, 'material': 'Ti', 'target_number': '2'},
    ],
    'steps': [
        PRE_SPUTTERING,
        {
            'uid': 'heat',
            'type': 'heating',
            'start_time': '09:30',
            'end_time': '10:00',
            **ARGON,
            'ramp_rate': 10,
            'temperature_setpoint': 300,
            'heater_output': 20,
            'pressure': 5e-3,
        },
        SPUTTERING,
        SPUTTERING_TI,
    ],
    'comments': {'comments': 'Ta and Ti from the 2" positions.'},
}


def messages(errors):
    return {error['path']: error['message'] for error in errors}


def _sections():
    return {s['key']: s for s in SPEC['sections']}


def _form(**changes):
    data = copy.deepcopy(FORM)
    data.update(changes)
    return data


def _files(data=None):
    return form_to_files(data or FORM, SPEC)


def _logbook(data=None):
    return _files(data)['files'][-1]['archive']['data']


# Spec


def test_entry_point_loads_app():
    assert sputter_logbook_dashboard_entry_point.external_url is None
    assert sputter_logbook_dashboard_entry_point.load() is not None
    assert (
        sputter_logbook_dashboard_entry_point.id_url_safe
        != pld_logbook_dashboard_entry_point.id_url_safe
    )


def test_spec_choices_match_schema():
    def schema_options(section, name):
        return set(section.m_def.all_quantities[name].type._list)

    sections = _sections()
    carrier = next(
        f for f in sections['chamber']['fields'] if f['key'] == 'substrate_carrier'
    )
    assert set(carrier['options']) == schema_options(SPSLogbook, 'substrate_carrier')
    sputtering = sections['steps']['variants']['sputtering']['fields']
    plasma = next(f for f in sputtering if f['key'] == 'plasma_type')
    assert set(plasma['options']) == schema_options(SputterPlasma, 'plasma_type')
    shutter = next(f for f in sputtering if f['key'] == 'shutter')
    assert set(shutter['options']) == schema_options(SPSSputteringStep, 'shutter')
    numbers = next(
        f for f in sections['targets']['fields'] if f['key'] == 'target_number'
    )
    assert numbers['options'] == ['1', '2', '3']


def test_spec_archive_paths_exist_in_schema():
    for variant in _sections()['steps']['variants'].values():
        for field in variant['fields']:
            if field['archive'] is None or 'gas' in field:
                continue
            for class_name in variant['sections'].values():
                quantity_of(getattr(sps_deposition, class_name), field['archive'])


@pytest.mark.parametrize(
    'section_key, section_cls',
    [
        ('samples', SampleInRun),
        ('run', SPSLogbook),
        ('chamber', SPSLogbook),
        ('comments', SPSLogbook),
    ],
)
def test_spec_section_archive_paths_exist_in_schema(section_key, section_cls):
    for field in _sections()[section_key]['fields']:
        if field['archive'] is None or field['kind'] in SKIPPED_KINDS:
            continue
        if field['kind'] == 'rows':
            assert field['archive'] in section_cls.m_def.all_sub_sections
            continue
        quantity_of(section_cls, field['archive'])


def test_spec_qualified_names_are_stable():
    assert SPEC['logbook_sections']['SPS'] == (
        'differ_pld4e_schemas.schema_packages.schema_package.SPSLogbook'
    )
    assert SPEC['reference_sections']['target'] == (
        'differ_pld4e_schemas.schema_packages.schema_package.SputterTarget'
    )
    assert 'in_situ' not in SPEC['reference_sections']


def test_steps_requested_for_sps():
    variants = _sections()['steps']['variants']
    assert list(variants) == ['pre_sputtering', 'heating', 'sputtering', 'cool_down']
    assert variants['sputtering']['prefill_from'] == 'pre_sputtering'


def test_client_settings_differ_from_pld():
    client = SPEC['client']
    assert client['title'] == 'Sputter logbook'
    assert client['draft_dir'] == 'sps_drafts'
    assert client['film_steps'] == ['sputtering']
    assert client['all_samples'] == ['SPS']
    diameter = next(
        f for f in client['target_entry']['fields'] if f['key'] == 'diameter'
    )
    assert diameter['scale'] == pytest.approx(0.0254)


# Validation


def test_complete_form_is_valid():
    assert validate(FORM, SPEC) == []


def test_system_defaults_to_sps():
    system = next(f for f in _sections()['run']['fields'] if f['key'] == 'system')
    assert system['default'] == 'SPS'


def test_empty_form_lists_missing_sections():
    errors = messages(validate({}, SPEC))
    assert errors['run.system'] == 'Required.'
    assert errors['samples'] == 'Add at least one sample.'
    assert 'targets' not in errors


def test_targets_required_with_a_sputter_step():
    data = _form(targets=[])
    assert messages(validate(data, SPEC))['targets'] == 'Add at least one target.'
    heating_only = _form(targets=[], steps=[FORM['steps'][1]])
    assert 'targets' not in messages(validate(heating_only, SPEC))


def test_mask_type_only_for_a_fixed_stage_with_mask():
    data = _form()
    data['chamber'].update(substrate_carrier='Fixed stage', mask_used=True)
    assert messages(validate(data, SPEC))['chamber.mask_type'] == 'Required.'
    data['chamber']['mask_type'] = 'Shadow mask 5 mm'
    assert validate(data, SPEC) == []
    data['chamber']['substrate_carrier'] = '1 cm² sub plate'
    data['chamber'].pop('mask_type')
    assert validate(data, SPEC) == []


def test_voltage_for_dc_and_load_capacitance_for_rf():
    step = FORM['steps'][0]
    dc = _form(steps=[{**step, 'voltage': None}])
    assert messages(validate(dc, SPEC))['steps.0.voltage'] == 'Required.'
    rf = _form(steps=[{**step, 'plasma_type': 'RF', 'voltage': None}])
    assert messages(validate(rf, SPEC))['steps.0.load_capacitance'] == 'Required.'
    both = _form(steps=[{**step, 'plasma_type': 'DC+RF'}])
    errors = messages(validate(both, SPEC))
    assert 'steps.0.voltage' not in errors
    assert errors['steps.0.load_capacitance'] == 'Required.'


def test_step_target_must_be_selected():
    data = _form(steps=[{**PRE_SPUTTERING, 'target': 'elsewhere'}])
    assert 'steps.0.target' in messages(validate(data, SPEC))


def test_target_number_is_one_of_the_positions():
    data = _form()
    data['targets'][1]['target_number'] = '4'
    assert (
        messages(validate(data, SPEC))['targets.1.target_number']
        == 'Choose one of the options.'
    )


def test_sample_id_and_name_from_sputtering_steps():
    sample = FORM['samples'][0]
    assert compute('sample_id', sample, FORM) == 'SPS_2026-10-22_09:15_S01'
    assert compute('sample_name', sample, FORM) == 'Si_Ta-50nm_Ti-10nm'


def test_sputtering_covers_all_samples():
    data = _form()
    data['samples'].append(
        {'uid': 'old', 'origin': 'Existing sample', 'sample': EXISTING}
    )
    sputtering = _logbook(data)['steps'][2]
    assert sputtering['samples'] == [
        f'../upload/archive/mainfile/{SAMPLE_FILE}#data',
        EXISTING,
    ]


def test_draft_needs_system_date_and_time():
    assert validate_draft(FORM, SPEC) == []
    assert {e['path'] for e in validate_draft({'run': {}}, SPEC)} == {
        'run.system',
        'run.date',
        'run.time',
    }


def test_draft_path():
    assert (
        draft_path(FORM) == 'sps_drafts/SPS_2026-10-22_0915_Ta-Ti_multilayer.draft.json'
    )


# Conversion


def test_files_are_samples_then_logbook():
    result = _files()
    assert [f['kind'] for f in result['files']] == ['sample', 'logbook']
    assert result['files'][0]['file_name'] == SAMPLE_FILE
    assert result['logbook_file'] == LOGBOOK_FILE


def test_logbook_archive_has_si_values():
    logbook = _logbook()
    assert logbook['m_def'].endswith('.SPSLogbook')
    assert logbook['pvd_system'] == 'SPS'
    assert logbook['base_pressure'] == pytest.approx(1e-5)
    assert logbook['description'] == 'Ta and Ti from the 2" positions.'
    assert logbook['targets'] == [
        {'target_number': 1, 'target': TA, 'material': 'Ta'},
        {'target_number': 2, 'target': TI, 'material': 'Ti'},
    ]
    assert 'laser_details' not in logbook
    assert 'in_situ_techniques' not in logbook
    pre, heating, sputtering, rf = logbook['steps']
    assert pre['m_def'].endswith('.SPSPreSputteringStep')
    assert pre['pressure'] == pytest.approx(0.5)
    assert pre['plasma'] == {
        'plasma_type': 'DC',
        'voltage': 380,
        'current': pytest.approx(0.26),
        'power': 100,
    }
    # 10 W per 5 minutes
    assert pre['ramp_up_rate'] == pytest.approx(2 / 60)
    assert pre['pre_sputter_time'] == pytest.approx(600)
    assert pre['background_gases'] == [
        {'gas': 'Ar', 'flow_setpoint': 20, 'flow_readout': 19.8}
    ]
    assert heating['temperature_setpoint'] == pytest.approx(573.15)
    assert sputtering['heater_stage_position'] == {
        'x': 0,
        'y': 0,
        'z': pytest.approx(0.1),
        'spin': 0,
    }
    assert sputtering['heater_rotation'] == pytest.approx(10)
    assert sputtering['shutter'] == 'open'
    assert sputtering['sputter_time'] == pytest.approx(1200)
    assert sputtering['film_thickness'] == pytest.approx(5e-8)
    assert rf['plasma']['load_capacitance'] == pytest.approx(1.2e-9)
    assert 'voltage' not in rf['plasma']


def test_logbook_archive_loads_and_normalizes_with_schema():
    archive = EntryArchive.m_from_dict({'data': _logbook()})
    archive.metadata = EntryMetadata()
    logbook = archive.data
    assert isinstance(logbook, SPSLogbook)
    assert isinstance(logbook.steps[0], SPSPreSputteringStep)
    assert logbook.steps[2].plasma.current.to('mA').magnitude == pytest.approx(260)
    assert logbook.steps[0].ramp_up_rate.to('W/minute').magnitude == pytest.approx(2)
    sample = logbook.samples[0]
    assert sample.name == 'Si_Ta-50nm_Ti-10nm'
    assert [layer.material for layer in sample.layers] == ['Ta', 'Ti']
    assert sample.layers[1].thickness.to('nm').magnitude == pytest.approx(10)


def test_sample_archive():
    sample = _files()['files'][0]['archive']['data']
    assert sample['m_def'].endswith('.Sample')
    assert sample['system'] == 'SPS'
    assert sample['sample_id'] == 'SPS_2026-10-22_09:15_S01'


def test_round_trip():
    form = archive_to_form(_logbook(), SPEC)
    assert form['run']['system'] == 'SPS'
    assert form['run']['date'] == '2026-10-22'
    assert form['chamber']['base_pressure'] == pytest.approx(1e-7)
    assert form['comments'] == {'comments': 'Ta and Ti from the 2" positions.'}
    assert [t['target_number'] for t in form['targets']] == ['1', '2']
    assert [s['type'] for s in form['steps']] == [
        'pre_sputtering',
        'heating',
        'sputtering',
        'sputtering',
    ]
    pre = form['steps'][0]
    assert pre['ramp_up_rate'] == pytest.approx(10)
    assert pre['pre_sputter_time'] == pytest.approx(10)
    assert pre['current'] == pytest.approx(260)
    assert pre['gas_Ar'] is True
    assert form['steps'][3]['load_capacitance'] == pytest.approx(1.2)
    # The form read back is complete again, once the samples are known.
    form['samples'][0]['substrate'] = SI_WAFER
    assert validate(form, SPEC) == []


def test_recipe():
    recipe = recipe_to_form(_logbook(), SPEC)
    assert recipe['system'] == 'SPS'
    assert len(recipe['steps']) == len(FORM['steps'])


def test_pld_logbook_is_rejected():
    with pytest.raises(ValueError, match='SPS'):
        archive_to_form({'m_def': 'x.SAPLDLogbook'}, SPEC)


# App


@pytest.fixture
def client():
    return TestClient(sputter_logbook_dashboard_entry_point.load())


def test_app_serves_page_and_spec(client):
    page = client.get('/').text
    assert '<title>Sputter logbook</title>' in page
    assert 'PLD logbook' not in page
    assert client.get('/static/app.js').status_code == HTTP_OK
    spec = client.get('/api/spec').json()
    assert spec['systems'] == ['SPS']
    assert spec['client']['title'] == 'Sputter logbook'


def test_app_builds_files(client):
    response = client.post('/api/archive', json={'form': FORM}).json()
    assert response['errors'] == []
    assert [f['kind'] for f in response['files']] == ['sample', 'logbook']


def test_app_names_drafts(client):
    response = client.post('/api/draft-name', json={'form': FORM}).json()
    assert response == {'errors': [], 'path': draft_path(FORM)}


def test_app_reads_logbook(client):
    response = client.post(
        '/api/form-from-archive', json={'data': _logbook(), 'mode': 'recipe'}
    )
    assert response.json()['system'] == 'SPS'
    response = client.post('/api/form-from-archive', json={'data': {'m_def': 'x.Y'}})
    assert response.status_code == HTTP_BAD_REQUEST
