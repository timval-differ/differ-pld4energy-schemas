import copy

import pytest
from fastapi.testclient import TestClient
from nomad.datamodel import EntryArchive, EntryMetadata
from structlog.testing import CapturingLogger

from differ_pld4e_schemas import pld_deposition
from differ_pld4e_schemas.dashboards import pld_logbook_dashboard_entry_point
from differ_pld4e_schemas.dashboards.pld_logbook import spec as spec_module
from differ_pld4e_schemas.dashboards.pld_logbook.convert import (
    archive_to_form,
    form_to_files,
    recipe_to_form,
)
from differ_pld4e_schemas.dashboards.pld_logbook.rules import (
    compute,
    validate,
)
from differ_pld4e_schemas.dashboards.pld_logbook.spec import form_spec
from differ_pld4e_schemas.laser import LaserCalibration, LaserParameters
from differ_pld4e_schemas.pld_deposition import (
    LAPLDDepositionStep,
    LAPLDLogbook,
    SAPLDLogbook,
)
from differ_pld4e_schemas.pld_substrate import NewSubstrate
from differ_pld4e_schemas.stages import PolarHeaterScan

SPEC = form_spec()
TARGET = '../uploads/u1/archive/target1#/data'
OTHER_TARGET = '../uploads/u1/archive/target2#/data'
EXPECTED_T1 = 0.42 / 0.5 / 0.92 * 100
EXPECTED_PULSES = 3000
HTTP_OK = 200
HTTP_BAD_REQUEST = 400
FILES_FOR_ONE_NEW_SUBSTRATE = 2

DEPOSITION = {
    'uid': 'step2',
    'type': 'deposition',
    'substrate': 'new:sub1',
    'target': TARGET,
    'x': 1,
    'y': 2,
    'z': 50,
    'tilt': 0,
    'spin': 0,
    'heater_scan_type': 'Polar scan',
    'radius_start': 0,
    'radius_stop': 40,
    'pulse_spacing': 0.5,
    'max_laser_frequency': 50,
    'number_of_scans': 10,
    'start_x_position': 0,
    'x_offset': 1,
    'start_y_position': 0,
    'y_offset': 1,
    'scan_area': 10,
    'substrate_temperature': 700,
    'pressure': 0.1,
    'gas_O2': True,
    'gas_O2_flow_setpoint': 5,
    'gas_O2_flow_readout': 4.9,
    'gas_O2_valve_position': 30,
    'gas_O2_valve_position_fixed': True,
    'magnification': '5X',
    'mask_size': '4x12',
    'spot_size': 2,
    'laser_fluence': 1.5,
    'laser_energy': 30,
    'attenuator_position': 60,
    'laser_frequency': 1,
    'number_of_laser_pulses': EXPECTED_PULSES,
    'laser_mode': 'HV NGR',
    'laser_voltage': 22,
}

FORM = {
    'run': {
        'system': 'LA-PLD',
        'name': 'STO on Si',
        'date': '2026-10-22',
        'base_pressure': 1e-8,
        'substrate_carrier': '4" wafer carrier',
        'particle_reduction_plate': 'in use',
    },
    'laser': {
        'energy_before_chamber': 500,
        'energy_after_chamber': 420,
        'transmission_window_2': 92,
        'transmission_window_1_manual': False,
    },
    'targets': [{'uid': 't1', 'target': TARGET, 'target_number': 2}],
    'substrates': [
        {
            'uid': 'sub1',
            'mode': 'Create new substrate',
            'sample_name': 'Si_STO-20nm',
            'run_number': '1',
            'sample_number': '1',
            'size': '10x10 mm',
            'substrate_material': 'Si',
        }
    ],
    'steps': [
        {
            'uid': 'step1',
            'type': 'heating',
            'ramp_rate': 10,
            'temperature_setpoint': 700,
            'pressure': 0.1,
        },
        DEPOSITION,
    ],
    'in_situ': {
        'rheed': True,
        'rheed_pattern_native_file': 'pld_files/run1/pattern.img',
        'la_eds': True,
        'la_eds_sp0_file': 'pld_files/run1/spectrum.sp0',
        'la_eds_energy_offset': 100,
        'la_eds_energy_per_channel': 10,
    },
}


def form(**changes):
    data = copy.deepcopy(FORM)
    for path, value in changes.items():
        *parents, key = path.split('__')
        target = data
        for parent in parents:
            target = target[int(parent)] if parent.isdigit() else target[parent]
        target[key] = value
    return data


def messages(errors):
    return {error['path']: error['message'] for error in errors}


# Spec


def test_entry_point_loads_app():
    assert pld_logbook_dashboard_entry_point.external_url is None
    assert pld_logbook_dashboard_entry_point.load() is not None


def test_spec_choices_match_schema():
    def schema_options(section, name):
        return set(section.m_def.all_quantities[name].type._list)

    assert set(spec_module.LASER_MODES) == schema_options(LaserParameters, 'laser_mode')
    assert set(spec_module.MASK_SIZES) == schema_options(LaserParameters, 'mask_size')
    assert set(spec_module.MAGNIFICATIONS) == schema_options(
        LaserParameters, 'magnification'
    )
    for system, section in spec_module.LOGBOOK_SECTIONS.items():
        assert set(spec_module.CARRIERS[system]) == schema_options(
            section, 'substrate_carrier'
        )


def test_spec_archive_paths_exist_in_schema():
    from differ_pld4e_schemas.dashboards.pld_logbook.convert import _quantity

    sections = {s['key']: s for s in SPEC['sections']}
    for variant in sections['steps']['variants'].values():
        for field in variant['fields']:
            if field['archive'] is None or 'gas' in field:
                continue
            resolved = []
            for system, class_name in variant['sections'].items():
                try:
                    _quantity(getattr(pld_deposition, class_name), field['archive'])
                    resolved.append(system)
                except KeyError:
                    pass
            if '/run/system' in str(field.get('visible_if')):
                assert resolved, field['key']
            else:
                assert len(resolved) == len(variant['sections']), field['key']


@pytest.mark.parametrize(
    'section_key, section_cls',
    [('laser', LaserCalibration), ('substrates', NewSubstrate)],
)
def test_spec_section_archive_paths_exist_in_schema(section_key, section_cls):
    from differ_pld4e_schemas.dashboards.pld_logbook.convert import (
        SKIPPED_KINDS,
        _quantity,
    )

    sections = {s['key']: s for s in SPEC['sections']}
    for field in sections[section_key]['fields']:
        if field['archive'] is None or field['kind'] in SKIPPED_KINDS:
            continue
        _quantity(section_cls, field['archive'])


def test_spec_qualified_names_are_stable():
    assert SPEC['logbook_sections']['LA-PLD'] == (
        'differ_pld4e_schemas.schema_packages.schema_package.LAPLDLogbook'
    )


# Validation


def test_complete_form_is_valid():
    assert validate(FORM, SPEC) == []


def test_empty_form_lists_missing_sections():
    errors = messages(validate({}, SPEC))
    assert errors['run.system'] == 'Required.'
    assert errors['targets'] == 'Add at least one target.'
    assert 'run.particle_reduction_plate' not in errors


def test_la_only_field_required_for_la():
    errors = messages(validate(form(run__particle_reduction_plate=None), SPEC))
    assert errors['run.particle_reduction_plate'] == 'Required.'


def test_la_fields_hidden_for_sa():
    data = form(run__system='SA-PLD', run__substrate_carrier='1" carrier')
    errors = messages(validate(data, SPEC))
    assert 'run.particle_reduction_plate' not in errors
    assert 'steps.1.radius_start' not in errors
    assert 'steps.1.heater_scan_type' not in errors


def test_carrier_options_depend_on_system():
    data = form(run__system='SA-PLD')
    errors = messages(validate(data, SPEC))
    assert errors['run.substrate_carrier'] == 'Choose one of the options.'


def test_polar_scan_fields_required_only_for_polar():
    errors = messages(validate(form(steps__1__radius_stop=None), SPEC))
    assert errors['steps.1.radius_stop'] == 'Required.'
    cartesian = form(steps__1__heater_scan_type='Cartesian scan')
    errors = messages(validate(cartesian, SPEC))
    assert 'steps.1.radius_stop' not in errors
    assert errors['steps.1.cartesian_scan_rate'] == 'Required.'


def test_sa_cartesian_scan_only_when_scanning():
    data = form(run__system='SA-PLD', run__substrate_carrier='1" carrier')
    data['run'].pop('particle_reduction_plate')
    assert messages(validate(data, SPEC)) == {}
    data['steps'][1]['substrate_stage_scan'] = True
    errors = messages(validate(data, SPEC))
    assert errors['steps.1.cartesian_x_offset'] == 'Required.'


def test_gas_fields_required_when_gas_is_ticked():
    errors = messages(validate(form(steps__1__gas_O2_flow_readout=None), SPEC))
    assert errors['steps.1.gas_O2_flow_readout'] == 'Required.'
    errors = messages(validate(form(steps__1__gas_Ar=True), SPEC))
    assert errors['steps.1.gas_Ar_valve_position'] == 'Required.'


def test_manual_transmission_required_when_manual():
    errors = messages(validate(form(laser__transmission_window_1_manual=True), SPEC))
    assert errors['laser.transmission_window_1'] == 'Required.'


def test_step_target_must_be_selected():
    errors = messages(validate(form(steps__1__target=OTHER_TARGET), SPEC))
    assert 'targets selected' in errors['steps.1.target']


def test_duplicate_targets_and_numbers():
    data = form()
    data['targets'].append({'uid': 't2', 'target': TARGET, 'target_number': 2})
    errors = messages(validate(data, SPEC))
    assert errors['targets.1.target'] == 'Target is used more than once.'
    assert errors['targets.1.target_number'] == 'Target number is used more than once.'


def test_duplicate_sample_user_id():
    data = form()
    data['substrates'].append(dict(data['substrates'][0], uid='sub2'))
    errors = messages(validate(data, SPEC))
    assert errors['substrates.1.sample_user_id'] == (
        'Sample user ID is used more than once.'
    )


def test_deposition_step_is_required():
    data = form()
    data['steps'] = data['steps'][:1]
    errors = messages(validate(data, SPEC))
    assert errors['steps'] == 'Add at least one pulsed laser deposition step.'


def test_in_situ_technique_needs_a_file():
    errors = messages(validate(form(in_situ__rheed_pattern_native_file=None), SPEC))
    assert errors['in_situ.rheed_pattern_native_file'] == 'Add at least one RHEED file.'


def test_invalid_numbers():
    errors = messages(validate(form(steps__1__number_of_laser_pulses=2.5), SPEC))
    assert errors['steps.1.number_of_laser_pulses'] == 'Enter a whole number.'
    errors = messages(validate(form(run__base_pressure='abc'), SPEC))
    assert errors['run.base_pressure'] == 'Enter a number.'


def test_computed_values():
    assert compute('transmission_window_1', FORM['laser'], FORM) == pytest.approx(
        EXPECTED_T1
    )
    assert (
        compute('sample_user_id', FORM['substrates'][0], FORM)
        == 'LA-PLD_2026-10-22_1_1'
    )


# Conversion


def _files():
    return form_to_files(FORM, SPEC)


def test_files_are_substrates_then_logbook():
    result = _files()
    assert [f['kind'] for f in result['files']] == ['substrate', 'logbook']
    assert result['files'][0]['file_name'] == 'LA-PLD_2026-10-22_1_1.archive.json'
    assert result['logbook_file'] == 'LA-PLD_2026-10-22_STO_on_Si.archive.json'


def test_logbook_archive_has_si_values():
    logbook = _files()['files'][-1]['archive']['data']
    assert logbook['pvd_system'] == 'LA-PLD'
    assert logbook['base_pressure'] == pytest.approx(1e-6)
    assert logbook['laser_details']['energy_before_chamber'] == pytest.approx(0.5)
    deposition = logbook['steps'][1]
    assert deposition['substrate_temperature'] == pytest.approx(973.15)
    assert deposition['laser']['spot_size'] == pytest.approx(2e-6)
    assert deposition['laser']['laser_fluence'] == pytest.approx(15000)
    assert deposition['polar_scan']['radius_stop'] == pytest.approx(0.04)
    assert 'cartesian_scan' not in deposition
    assert deposition['background_gases'] == [
        {
            'gas': 'O2',
            'flow_setpoint': 5,
            'flow_readout': 4.9,
            'valve_position': 30,
            'valve_position_fixed': True,
        }
    ]
    assert deposition['substrate'] == (
        '../upload/archive/mainfile/LA-PLD_2026-10-22_1_1.archive.json#data'
    )


def test_logbook_archive_loads_and_normalizes_with_schema():
    data = _files()['files'][-1]['archive']['data']
    archive = EntryArchive.m_from_dict({'data': data})
    archive.metadata = EntryMetadata()
    logbook = archive.data
    assert isinstance(logbook, LAPLDLogbook)
    assert isinstance(logbook.steps[1], LAPLDDepositionStep)
    assert isinstance(logbook.steps[1].polar_scan, PolarHeaterScan)
    assert logbook.steps[1].laser.number_of_laser_pulses == EXPECTED_PULSES
    logbook.laser_details.normalize(archive, CapturingLogger())
    assert logbook.laser_details.transmission_window_1 == pytest.approx(EXPECTED_T1)
    assert logbook.in_situ_techniques.la_eds[0].sp0_file.endswith('spectrum.sp0')


def test_substrate_archive():
    files = _files()['files']
    substrate = files[0]['archive']['data']
    assert substrate['pvd_system'] == 'LA-PLD'
    assert substrate['sample_user_id'] == 'LA-PLD_2026-10-22_1_1'
    logbook = files[-1]['archive']['data']
    assert logbook['substrates'][0]['sample_uuid'] == substrate['sample_uuid']


def test_existing_substrates_are_not_created_again():
    data = form(substrates__0__ref='../upload/archive/abc#/data')
    result = form_to_files(data, SPEC)
    assert [f['kind'] for f in result['files']] == ['logbook']
    assert result['files'][0]['archive']['data']['steps'][1]['substrate'] == (
        '../upload/archive/abc#/data'
    )


def test_round_trip():
    logbook = _files()['files'][-1]['archive']['data']
    loaded = archive_to_form(logbook, SPEC)
    assert {k: v for k, v in loaded['run'].items() if k != 'base_pressure'} == {
        k: v for k, v in FORM['run'].items() if k != 'base_pressure'
    }
    assert loaded['run']['base_pressure'] == pytest.approx(1e-8)
    step = loaded['steps'][1]
    assert step['type'] == 'deposition'
    assert step['substrate_temperature'] == pytest.approx(700)
    assert step['gas_O2'] is True
    assert step['gas_O2_flow_readout'] == pytest.approx(4.9)
    assert step['substrate'] == f'new:{loaded["substrates"][0]["uid"]}'
    assert loaded['in_situ']['rheed'] is True
    assert validate(loaded, SPEC) == []


def test_recipe_drops_substrates():
    logbook = _files()['files'][-1]['archive']['data']
    recipe = recipe_to_form(logbook, SPEC)
    assert recipe['system'] == 'LA-PLD'
    assert [s['type'] for s in recipe['steps']] == ['heating', 'deposition']
    assert 'substrate' not in recipe['steps'][1]


def test_non_logbook_archive_is_rejected():
    with pytest.raises(ValueError):
        archive_to_form({'m_def': 'something.Else'}, SPEC)


def test_sa_logbook_section():
    data = form(run__system='SA-PLD', run__substrate_carrier='1" carrier')
    logbook = form_to_files(data, SPEC)['files'][-1]['archive']['data']
    archive = EntryArchive.m_from_dict({'data': logbook})
    assert isinstance(archive.data, SAPLDLogbook)
    assert 'particle_reduction_plate' not in logbook


# App


@pytest.fixture
def client():
    return TestClient(pld_logbook_dashboard_entry_point.load())


def test_app_serves_page_and_spec(client):
    assert 'PLD logbook' in client.get('/').text
    assert client.get('/static/app.js').status_code == HTTP_OK
    assert client.get('/api/spec').json()['systems'] == ['SA-PLD', 'LA-PLD']


def test_app_refuses_incomplete_form(client):
    response = client.post('/api/archive', json={'form': {}}).json()
    assert response['files'] == []
    assert response['errors']


def test_app_builds_files(client):
    response = client.post('/api/archive', json={'form': FORM}).json()
    assert response['errors'] == []
    assert len(response['files']) == FILES_FOR_ONE_NEW_SUBSTRATE


def test_app_reads_logbook(client):
    logbook = _files()['files'][-1]['archive']['data']
    response = client.post(
        '/api/form-from-archive', json={'data': logbook, 'mode': 'recipe'}
    )
    assert response.json()['system'] == 'LA-PLD'
    response = client.post('/api/form-from-archive', json={'data': {'m_def': 'x.Y'}})
    assert response.status_code == HTTP_BAD_REQUEST
