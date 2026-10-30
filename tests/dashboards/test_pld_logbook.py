import copy
import re

import pytest
from fastapi.testclient import TestClient
from nomad.datamodel import EntryArchive, EntryMetadata
from structlog.testing import CapturingLogger

from differ_pld4e_schemas import pld_deposition
from differ_pld4e_schemas.dashboards import pld_logbook_dashboard_entry_point
from differ_pld4e_schemas.dashboards.common.archive import SKIPPED_KINDS, quantity_of
from differ_pld4e_schemas.dashboards.pld_logbook import spec as spec_module
from differ_pld4e_schemas.dashboards.pld_logbook.convert import (
    archive_to_form,
    draft_path,
    form_to_files,
    recipe_to_form,
)
from differ_pld4e_schemas.dashboards.pld_logbook.rules import (
    compute,
    section_requirement,
    validate,
    validate_draft,
)
from differ_pld4e_schemas.dashboards.pld_logbook.spec import form_spec
from differ_pld4e_schemas.gas import GASES
from differ_pld4e_schemas.laser import LaserCalibration, LaserParameters
from differ_pld4e_schemas.pld_deposition import (
    LAPLDDepositionStep,
    LAPLDLogbook,
    SAPLDLogbook,
)
from differ_pld4e_schemas.sample import SampleInRun
from differ_pld4e_schemas.stages import PolarHeaterScan

SPEC = form_spec()
TARGET = '../uploads/u1/archive/target1#/data'
OTHER_TARGET = '../uploads/u1/archive/target2#/data'
EXISTING = '../uploads/u0/archive/sample0#/data'
SI_WAFER = '../uploads/u0/archive/substrate_si#/data'
EXPECTED_T1 = 0.42 / 0.5 / 0.92 * 100
EXPECTED_PULSES = 3000
HTTP_OK = 200
HTTP_BAD_REQUEST = 400
FILES_FOR_ONE_NEW_SAMPLE = 2
SAMPLE_FILE = 'LA-PLD_2026-10-22_09_15_S01.archive.json'

GAS_O2 = {
    'atmosphere': 'Background gas',
    'gas_O2': True,
    'gas_O2_flow_setpoint': 5,
    'gas_O2_flow_readout': 4.9,
    'valve_position': 30,
    'valve_position_fixed': True,
}

TARGET_STAGE = {
    'start_x_position': 0,
    'x_offset': 1,
    'start_y_position': 0,
    'y_offset': 1,
    'start_z_position': 5,
    'scan_width_x': 10,
    'scan_width_y': 8,
    'scan_speed_x': 2,
    'scan_speed_y': 1.5,
}

LASER = {
    'laser_mode': 'HV NGR',
    'laser_voltage': 22,
    'magnification': '5X',
    'mask_size': '5x18',
    'spot_size': 2,
    'laser_fluence': 1.5,
    'laser_energy': 30,
    'attenuator_position': 60,
    'laser_frequency': 1,
    'number_of_laser_pulses': EXPECTED_PULSES,
}

DEPOSITION = {
    'uid': 'step2',
    'type': 'deposition',
    'sample': 'new:sub1',
    'target': TARGET,
    'film_thickness': 20,
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
    **TARGET_STAGE,
    'substrate_temperature': 700,
    'pressure': 0.1,
    **GAS_O2,
    **LASER,
}

FORM = {
    'run': {
        'operator_name': 'Ada Lovelace',
        'operator_email': 'ada@example.org',
        'system': 'LA-PLD',
        'name': 'STO on Si',
        'date': '2026-10-22',
        'time': '09:15',
        'utc_offset': '+02:00',
    },
    'samples': [
        {
            'uid': 'sub1',
            'origin': 'New sample',
            'substrate': SI_WAFER,
            # Copied by the browser from the chosen substrate.
            'substrate_material': 'Si',
        }
    ],
    'chamber': {
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
    # The material is copied by the browser from the chosen target.
    'targets': [
        {'uid': 't1', 'target': TARGET, 'target_number': '2', 'material': 'SrTiO3'}
    ],
    'steps': [
        {
            'uid': 'step1',
            'type': 'heating',
            'ramp_rate': 10,
            'temperature_setpoint': 700,
            'heater_output': 35,
            'pressure': 0.1,
            **GAS_O2,
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

ANNEALING = {
    'uid': 'anneal',
    'type': 'annealing',
    'atmosphere': 'UHV',
    'temperature_setpoint': 600,
    'heater_output': 40,
    'dwell_time': 30,
    'pressure': 1e-8,
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


def sa_form(**changes):
    data = form(
        run__system='SA-PLD', chamber__substrate_carrier='1" carrier', **changes
    )
    data['chamber'].pop('particle_reduction_plate')
    return data


def annealing_form():
    data = sa_form()
    data['steps'] = [ANNEALING]
    data['laser'] = {}
    data['targets'] = [{'uid': 't1'}]
    return data


def messages(errors):
    return {error['path']: error['message'] for error in errors}


def _sections():
    return {s['key']: s for s in SPEC['sections']}


def _logbook(data=None):
    return form_to_files(data or FORM, SPEC)['files'][-1]['archive']['data']


# Spec


def test_entry_point_loads_app():
    assert pld_logbook_dashboard_entry_point.external_url is None
    assert pld_logbook_dashboard_entry_point.load() is not None


def test_spec_choices_match_schema():
    def schema_options(section, name):
        return set(section.m_def.all_quantities[name].type._list)

    assert set(spec_module.LASER_MODES) == schema_options(LaserParameters, 'laser_mode')
    assert set(spec_module.MASK_SIZES) == schema_options(LaserParameters, 'mask_size')
    assert '5x18' in spec_module.MASK_SIZES
    assert set(spec_module.MAGNIFICATIONS) == schema_options(
        LaserParameters, 'magnification'
    )
    for system, section in spec_module.LOGBOOK_SECTIONS.items():
        assert set(spec_module.CARRIERS[system]) == schema_options(
            section, 'substrate_carrier'
        )


def test_spec_archive_paths_exist_in_schema():
    for variant in _sections()['steps']['variants'].values():
        for field in variant['fields']:
            if field['archive'] is None or 'gas' in field:
                continue
            resolved = []
            for system, class_name in variant['sections'].items():
                try:
                    quantity_of(getattr(pld_deposition, class_name), field['archive'])
                    resolved.append(system)
                except KeyError:
                    pass
            if '/run/system' in str(field.get('visible_if')):
                assert resolved, field['key']
            else:
                assert len(resolved) == len(variant['sections']), field['key']


@pytest.mark.parametrize(
    'section_key, section_cls',
    [
        ('laser', LaserCalibration),
        ('samples', SampleInRun),
        ('run', SAPLDLogbook),
        ('chamber', LAPLDLogbook),
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
    assert SPEC['logbook_sections']['LA-PLD'] == (
        'differ_pld4e_schemas.schema_packages.schema_package.LAPLDLogbook'
    )
    assert SPEC['reference_sections']['sample'] == (
        'differ_pld4e_schemas.schema_packages.schema_package.Sample'
    )


def test_run_comes_first_then_samples_then_system():
    keys = [s['key'] for s in SPEC['sections']]
    assert keys[:3] == ['run', 'samples', 'chamber']


# Validation


def test_complete_form_is_valid():
    assert validate(FORM, SPEC) == []


def test_empty_form_lists_missing_sections():
    errors = messages(validate({}, SPEC))
    assert errors['run.system'] == 'Required.'
    assert errors['samples'] == 'Add at least one sample.'
    assert 'targets' not in errors
    assert 'chamber.particle_reduction_plate' not in errors


def test_la_only_field_required_for_la():
    errors = messages(validate(form(chamber__particle_reduction_plate=None), SPEC))
    assert errors['chamber.particle_reduction_plate'] == 'Required.'


def test_la_fields_hidden_for_sa():
    errors = messages(validate(sa_form(), SPEC))
    assert errors == {}


def test_carrier_options_depend_on_system():
    data = form(run__system='SA-PLD')
    errors = messages(validate(data, SPEC))
    assert errors['chamber.substrate_carrier'] == 'Choose one of the options.'


def test_polar_scan_fields_required_only_for_polar():
    errors = messages(validate(form(steps__1__radius_stop=None), SPEC))
    assert errors['steps.1.radius_stop'] == 'Required.'
    cartesian = form(steps__1__heater_scan_type='Cartesian scan')
    errors = messages(validate(cartesian, SPEC))
    assert 'steps.1.radius_stop' not in errors
    assert errors['steps.1.cartesian_scan_rate'] == 'Required.'


def test_sa_substrate_stage_scan_has_widths_and_speeds():
    data = sa_form()
    data['steps'][1]['substrate_stage_scan'] = True
    errors = messages(validate(data, SPEC))
    for key in ('scan_width_x', 'scan_width_y', 'scan_speed_x', 'scan_speed_y'):
        assert errors[f'steps.1.substrate_{key}'] == 'Required.'


def test_target_stage_has_z_widths_and_speeds():
    errors = messages(validate(form(steps__1__start_z_position=None), SPEC))
    assert errors['steps.1.start_z_position'] == 'Required.'
    keys = {f['key'] for f in spec_module.target_stage_fields()}
    assert 'scan_area' not in keys
    assert {'scan_speed_x', 'scan_speed_y', 'scan_width_x', 'scan_width_y'} <= keys


def test_gas_fields_required_when_gas_is_ticked():
    errors = messages(validate(form(steps__1__gas_O2_flow_readout=None), SPEC))
    assert errors['steps.1.gas_O2_flow_readout'] == 'Required.'
    errors = messages(validate(form(steps__1__gas_Ar=True), SPEC))
    assert errors['steps.1.gas_Ar_flow_setpoint'] == 'Required.'
    assert 'steps.1.gas_Ar_valve_position' not in errors


def test_one_valve_position_for_all_gases():
    errors = messages(validate(form(steps__1__valve_position=None), SPEC))
    assert errors['steps.1.valve_position'] == 'Required.'
    no_gas = form(steps__1__gas_O2=False, steps__1__valve_position=None)
    assert 'steps.1.valve_position' not in messages(validate(no_gas, SPEC))


def test_uhv_needs_only_the_pressure():
    data = form(steps__1__atmosphere='UHV', steps__1__gas_O2_flow_readout=None)
    data['steps'][1].pop('valve_position')
    assert validate(data, SPEC) == []
    deposition = _logbook(data)['steps'][1]
    assert deposition['atmosphere'] == 'UHV'
    assert deposition['background_gases'] == []
    assert 'valve_position' not in deposition


def test_heating_records_heater_output():
    errors = messages(validate(form(steps__0__heater_output=None), SPEC))
    assert errors['steps.0.heater_output'] == 'Required.'


def test_manual_transmission_required_when_manual():
    errors = messages(validate(form(laser__transmission_window_1_manual=True), SPEC))
    assert errors['laser.transmission_window_1'] == 'Required.'


def test_step_target_must_be_selected():
    errors = messages(validate(form(steps__1__target=OTHER_TARGET), SPEC))
    assert 'targets selected' in errors['steps.1.target']


def test_duplicate_targets_and_numbers():
    data = form()
    data['targets'].append({'uid': 't2', 'target': TARGET, 'target_number': '2'})
    errors = messages(validate(data, SPEC))
    assert errors['targets.1.target'] == 'Target is used more than once.'
    assert errors['targets.1.target_number'] == 'Target number is used more than once.'


def test_invalid_numbers_and_time():
    errors = messages(validate(form(steps__1__number_of_laser_pulses=2.5), SPEC))
    assert errors['steps.1.number_of_laser_pulses'] == 'Enter a whole number.'
    errors = messages(validate(form(chamber__base_pressure='abc'), SPEC))
    assert errors['chamber.base_pressure'] == 'Enter a number.'
    errors = messages(validate(form(run__time='25:00'), SPEC))
    assert errors['run.time'] == 'Enter a time (hh:mm).'


def test_computed_transmission():
    assert compute('transmission_window_1', FORM['laser'], FORM) == pytest.approx(
        EXPECTED_T1
    )


# Laser and targets follow the process steps


def test_annealing_only_run_needs_no_laser_or_targets():
    data = annealing_form()
    sections = _sections()
    assert section_requirement(sections['laser'], SPEC, data) == 'none'
    assert section_requirement(sections['targets'], SPEC, data) == 'none'
    assert validate(data, SPEC) == []
    logbook = _logbook(data)
    assert 'laser_details' not in logbook
    assert 'targets' not in logbook
    assert logbook['steps'][0]['m_def'].endswith('.SAPLDAnnealingStep')
    assert logbook['steps'][0]['dwell_time'] == pytest.approx(1800)


def test_run_without_steps_is_valid():
    data = annealing_form()
    data['steps'] = []
    assert validate(data, SPEC) == []


def test_laser_and_targets_required_with_deposition():
    data = form(laser={'transmission_window_1_manual': False}, targets=[])
    errors = messages(validate(data, SPEC))
    assert errors['laser.energy_before_chamber'] == 'Required.'
    assert errors['targets'] == 'Add at least one target.'


def test_optional_laser_step():
    spec = copy.deepcopy(SPEC)
    steps = next(s for s in spec['sections'] if s['key'] == 'steps')
    steps['variants']['laser_anneal'] = spec_module.variant(
        'Laser annealing',
        {'SA-PLD': 'SAPLDAnnealingStep', 'LA-PLD': 'LAPLDAnnealingStep'},
        [*spec_module.laser_fields(), spec_module.pressure('Pressure')],
        laser='optional',
        laser_keys={f['key'] for f in spec_module.laser_fields()},
    )
    sections = {s['key']: s for s in spec['sections']}
    data = annealing_form()
    data['steps'] = [{'uid': 'l1', 'type': 'laser_anneal', 'pressure': 1}]
    assert section_requirement(sections['laser'], spec, data) == 'optional'
    assert validate(data, spec) == []
    data['steps'][0]['laser_used'] = True
    assert section_requirement(sections['laser'], spec, data) == 'required'
    errors = messages(validate(data, spec))
    assert errors['steps.0.laser_frequency'] == 'Required.'
    assert errors['laser.energy_before_chamber'] == 'Required.'


# Samples


def test_sample_id_and_name():
    data = form()
    data['samples'] += [
        {'uid': 'old', 'origin': 'Existing sample', 'sample': EXISTING},
        {'uid': 'ext', 'origin': 'External sample', 'substrate_details': 'FTO'},
    ]
    assert compute('sample_id', data['samples'][0], data) == (
        'LA-PLD_2026-10-22_09:15_S01'
    )
    # Existing samples keep their own ID and do not take a number.
    assert compute('sample_id', data['samples'][2], data) == (
        'LA-PLD_2026-10-22_09:15_S02'
    )
    assert compute('sample_name', data['samples'][0], data) == 'Si_SrTiO3-20nm'
    assert compute('sample_name', data['samples'][2], data) == 'FTO'


def test_sample_needs_a_substrate():
    errors = messages(validate(form(samples__0__substrate=None), SPEC))
    assert errors['samples.0.substrate'] == 'Required.'


def test_deposition_step_records_the_film_thickness():
    errors = messages(validate(form(steps__1__film_thickness=None), SPEC))
    assert errors['steps.1.film_thickness'] == 'Required.'
    assert _logbook()['steps'][1]['film_thickness'] == pytest.approx(2e-8)


def test_films_come_from_the_deposition_steps():
    second = dict(DEPOSITION, uid='step3', target=OTHER_TARGET, film_thickness=5)
    data = form()
    data['targets'].append(
        {'uid': 't2', 'target': OTHER_TARGET, 'target_number': '3', 'material': 'YSZ'}
    )
    data['steps'].append(second)
    data['samples'].append(
        {
            'uid': 'sub2',
            'origin': 'New sample',
            'substrate': SI_WAFER,
            'substrate_material': 'Si',
        }
    )
    # LA-PLD: each deposition step grows its film on the step's sample.
    assert compute('sample_name', data['samples'][0], data) == 'Si_SrTiO3-20nm_YSZ-5nm'
    assert compute('sample_name', data['samples'][1], data) == 'Si'
    # SA-PLD: a deposition covers all samples in the chamber.
    data['run']['system'] = 'SA-PLD'
    assert compute('sample_name', data['samples'][1], data) == 'Si_SrTiO3-20nm_YSZ-5nm'


def test_external_sample_can_come_with_films():
    data = form(
        samples__0__origin='External sample',
        samples__0__substrate=None,
        samples__0__substrate_details='MgO',
    )
    data['samples'][0]['prior_films'] = [{'material': 'SrRuO3', 'thickness': 10}]
    assert validate(data, SPEC) == []
    item = data['samples'][0]
    assert compute('sample_name', item, data) == 'MgO_SrRuO3-10nm_SrTiO3-20nm'
    files = form_to_files(data, SPEC)['files']
    sample, logbook = files[0]['archive']['data'], files[-1]['archive']['data']
    # The Sample entry has the whole stack, the logbook keeps both apart.
    assert [layer['material'] for layer in sample['layers']] == ['SrRuO3', 'SrTiO3']
    assert logbook['samples'][0]['prior_layers'] == [
        {'material': 'SrRuO3', 'thickness': pytest.approx(1e-8)}
    ]
    assert [layer['material'] for layer in logbook['samples'][0]['layers']] == [
        'SrTiO3'
    ]
    loaded = archive_to_form(logbook, SPEC)
    assert loaded['samples'][0]['prior_films'] == [
        {'material': 'SrRuO3', 'thickness': 10}
    ]
    data['samples'][0]['prior_films'].append({'thickness': 3})
    errors = messages(validate(data, SPEC))
    assert errors['samples.0.prior_films.1.material'] == 'Required.'


def test_only_external_samples_list_films_they_came_with():
    data = form()
    data['samples'][0]['prior_films'] = [{'material': 'SrRuO3', 'thickness': 10}]
    assert compute('sample_name', data['samples'][0], data) == 'Si_SrTiO3-20nm'
    assert 'prior_layers' not in _logbook(data)['samples'][0]


def test_samples_have_no_film_list_of_their_own():
    fields = {f['key'] for f in _sections()['samples']['fields']}
    assert 'layers' not in fields
    assert 'prior_films' in fields


def test_external_sample_substrate_is_from_the_database_or_described():
    data = form(samples__0__origin='External sample', samples__0__substrate=None)
    errors = messages(validate(data, SPEC))
    assert 'samples.0.substrate' not in errors
    assert errors['samples.0.substrate_details'] == 'Required.'
    data = form(samples__0__origin='External sample')
    assert validate(data, SPEC) == []


def test_substrates_and_targets_come_from_the_databases():
    fields = {f['key']: f for f in _sections()['samples']['fields']}
    assert fields['substrate']['kind'] == 'reference'
    assert fields['substrate']['reference'] == 'substrate'
    assert fields['substrate']['ref_copy'] == {'substrate_material': 'material'}
    target = {f['key']: f for f in _sections()['targets']['fields']}['target']
    assert target['ref_copy'] == {'material': 'material'}
    assert SPEC['reference_sections']['substrate'].endswith('.SubstrateType')


def test_target_number_is_one_of_the_positions():
    fields = {f['key']: f for f in _sections()['targets']['fields']}
    assert fields['target_number']['options'] == ['1', '2', '3', '4', '5']
    errors = messages(validate(form(targets__0__target_number='6'), SPEC))
    assert errors['targets.0.target_number'] == 'Choose one of the options.'
    assert _logbook()['targets'][0]['target_number'] == 2  # noqa: PLR2004


def test_existing_sample_is_chosen():
    data = form(samples__0__origin='Existing sample')
    errors = messages(validate(data, SPEC))
    assert errors['samples.0.sample'] == 'Required.'
    assert 'samples.0.substrate' not in errors


def test_the_same_existing_sample_twice():
    data = form()
    data['samples'] = [
        {'uid': 'a', 'origin': 'Existing sample', 'sample': EXISTING},
        {'uid': 'b', 'origin': 'Existing sample', 'sample': EXISTING},
    ]
    data['steps'][1]['sample'] = EXISTING
    errors = messages(validate(data, SPEC))
    assert errors['samples.1.sample'] == 'Existing sample is used more than once.'


def test_la_deposition_sample_must_be_in_the_run():
    errors = messages(validate(form(steps__1__sample='new:other'), SPEC))
    assert errors['steps.1.sample'] == 'Choose one of the samples under Samples.'


# In-situ data may follow later


def test_in_situ_technique_without_files_is_valid():
    data = form(in_situ__rheed_pattern_native_file=None)
    assert validate(data, SPEC) == []
    logbook = _logbook(data)
    assert logbook['in_situ_techniques']['rheed'] == [{}]


# Drafts


def test_draft_needs_system_date_and_time():
    errors = messages(validate_draft({'run': {'system': 'SA-PLD'}}, SPEC))
    assert set(errors) == {'run.date', 'run.time'}
    assert validate_draft(FORM, SPEC) == []


def test_draft_path_is_stable():
    assert draft_path(FORM) == 'pld_drafts/LA-PLD_2026-10-22_0915_STO_on_Si.draft.json'
    assert draft_path(form(samples=[], steps=[])) == draft_path(FORM)


# Conversion


def _files(data=None):
    return form_to_files(data or FORM, SPEC)


def test_files_are_samples_then_logbook():
    result = _files()
    assert [f['kind'] for f in result['files']] == ['sample', 'logbook']
    assert result['files'][0]['file_name'] == SAMPLE_FILE
    assert result['files'][0]['overwrite'] is False
    assert result['logbook_file'] == 'LA-PLD_2026-10-22_0915_STO_on_Si.archive.json'


def test_logbook_archive_has_si_values():
    logbook = _logbook()
    assert logbook['pvd_system'] == 'LA-PLD'
    assert logbook['datetime'] == '2026-10-22T09:15:00+02:00'
    assert logbook['operator_name'] == 'Ada Lovelace'
    assert logbook['base_pressure'] == pytest.approx(1e-6)
    assert logbook['laser_details']['energy_before_chamber'] == pytest.approx(0.5)
    deposition = logbook['steps'][1]
    assert deposition['substrate_temperature'] == pytest.approx(973.15)
    assert deposition['laser']['spot_size'] == pytest.approx(2e-6)
    assert deposition['laser']['laser_fluence'] == pytest.approx(15000)
    assert deposition['laser']['mask_size'] == '5x18'
    assert deposition['polar_scan']['radius_stop'] == pytest.approx(0.04)
    assert deposition['target_stage']['start_z_position'] == pytest.approx(0.005)
    assert deposition['target_stage']['scan_speed_x'] == pytest.approx(0.002)
    assert 'cartesian_scan' not in deposition
    assert deposition['valve_position'] == pytest.approx(30)
    assert deposition['valve_position_fixed'] is True
    assert deposition['background_gases'] == [
        {'gas': 'O2', 'flow_setpoint': 5, 'flow_readout': 4.9}
    ]
    assert deposition['samples'] == [f'../upload/archive/mainfile/{SAMPLE_FILE}#data']
    assert logbook['steps'][0]['heater_output'] == pytest.approx(35)


def test_sa_deposition_covers_all_samples():
    data = sa_form()
    data['samples'].append(
        {'uid': 'old', 'origin': 'Existing sample', 'sample': EXISTING}
    )
    deposition = _logbook(data)['steps'][1]
    assert deposition['samples'] == [
        '../upload/archive/mainfile/SA-PLD_2026-10-22_09_15_S01.archive.json#data',
        EXISTING,
    ]


def test_logbook_archive_loads_and_normalizes_with_schema():
    data = _logbook()
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
    assert logbook.samples[0].layers[0].thickness.to('nm').magnitude == (
        pytest.approx(20)
    )


def test_sample_archive():
    files = _files()['files']
    sample = files[0]['archive']['data']
    assert sample['m_def'].endswith('.Sample')
    assert sample['system'] == 'LA-PLD'
    assert sample['sample_id'] == 'LA-PLD_2026-10-22_09:15_S01'
    assert sample['name'] == 'Si_SrTiO3-20nm'
    assert sample['substrate'] == SI_WAFER
    assert sample['substrate_material'] == 'Si'
    assert sample['layers'] == [
        {'target': TARGET, 'material': 'SrTiO3', 'thickness': pytest.approx(2e-8)}
    ]
    logbook = files[-1]['archive']['data']
    assert logbook['samples'][0]['sample_uuid'] == sample['sample_uuid']


def test_saved_samples_are_updated_but_existing_never():
    reference = f'../upload/archive/mainfile/{SAMPLE_FILE}#data'
    data = form(
        samples__0__ref=reference,
        samples__0__sample_id='LA-PLD_2026-10-22_09:15_S01',
        run__time='10:00',
    )
    data['samples'].append(
        {'uid': 'old', 'origin': 'Existing sample', 'sample': EXISTING}
    )
    files = form_to_files(data, SPEC)['files']
    assert [f['kind'] for f in files] == ['sample', 'logbook']
    assert files[0]['file_name'] == SAMPLE_FILE
    assert files[0]['overwrite'] is True
    # Once its entry exists, a sample keeps its ID when the run time changes.
    assert files[0]['archive']['data']['sample_id'] == 'LA-PLD_2026-10-22_09:15_S01'
    assert files[-1]['archive']['data']['samples'][1]['sample'] == EXISTING


def test_round_trip():
    loaded = archive_to_form(_logbook(), SPEC)
    run = loaded['run']
    assert run.pop('start') == '2026-10-22T09:15:00+02:00'
    expected = {k: v for k, v in FORM['run'].items() if k != 'utc_offset'}
    assert run == expected
    assert loaded['chamber']['base_pressure'] == pytest.approx(1e-8)
    step = loaded['steps'][1]
    assert step['type'] == 'deposition'
    assert step['substrate_temperature'] == pytest.approx(700)
    assert step['gas_O2'] is True
    assert step['gas_O2_flow_readout'] == pytest.approx(4.9)
    assert step['valve_position'] == pytest.approx(30)
    assert step['sample'] == f'new:{loaded["samples"][0]["uid"]}'
    assert compute('sample_name', loaded['samples'][0], loaded) == 'Si_SrTiO3-20nm'
    assert loaded['steps'][1]['film_thickness'] == pytest.approx(20)
    assert loaded['samples'][0]['substrate'] == SI_WAFER
    assert loaded['samples'][0]['substrate_material'] == 'Si'
    assert loaded['targets'][0]['target_number'] == '2'
    assert loaded['in_situ']['rheed'] is True
    loaded['run']['utc_offset'] = '+02:00'
    assert validate(loaded, SPEC) == []


def test_recipe_drops_samples():
    recipe = recipe_to_form(_logbook(), SPEC)
    assert recipe['system'] == 'LA-PLD'
    assert [s['type'] for s in recipe['steps']] == ['heating', 'deposition']
    assert 'sample' not in recipe['steps'][1]


def test_non_logbook_archive_is_rejected():
    with pytest.raises(ValueError):
        archive_to_form({'m_def': 'something.Else'}, SPEC)


def test_sa_logbook_section():
    logbook = _logbook(sa_form())
    archive = EntryArchive.m_from_dict({'data': logbook})
    assert isinstance(archive.data, SAPLDLogbook)
    assert 'particle_reduction_plate' not in logbook


def test_every_gas_is_in_the_gas_block():
    keys = {f['key'] for f in spec_module.gas_fields()}
    assert {f'gas_{gas}' for gas in GASES} <= keys


# App


@pytest.fixture
def client():
    return TestClient(pld_logbook_dashboard_entry_point.load())


def test_app_serves_page_and_spec(client):
    assert 'PLD logbook' in client.get('/').text
    assert client.get('/static/app.js').status_code == HTTP_OK
    assert client.get('/api/spec').json()['systems'] == ['SA-PLD', 'LA-PLD']


def test_page_loads_current_assets(client):
    response = client.get('/')
    assert response.headers['cache-control'] == 'no-cache'
    assert re.search(r'static/app\.js\?v=[0-9a-f]{12}"', response.text)
    assert re.search(r'static/style\.css\?v=[0-9a-f]{12}"', response.text)


def test_page_and_server_report_the_same_script_version(client):
    page = client.get('/').text
    version = re.search(r'name="script-version" content="([0-9a-f]{12})"', page)
    assert version
    assert client.get('/api/spec').json()['script_version'] == version.group(1)


def test_app_refuses_incomplete_form(client):
    response = client.post('/api/archive', json={'form': {}}).json()
    assert response['files'] == []
    assert response['errors']


def test_app_builds_files(client):
    response = client.post('/api/archive', json={'form': FORM}).json()
    assert response['errors'] == []
    assert len(response['files']) == FILES_FOR_ONE_NEW_SAMPLE


def test_app_names_drafts(client):
    response = client.post('/api/draft-name', json={'form': FORM}).json()
    assert response == {'errors': [], 'path': draft_path(FORM)}
    response = client.post('/api/draft-name', json={'form': {'run': {}}}).json()
    assert response['path'] is None
    assert response['errors']


def test_app_reads_logbook(client):
    response = client.post(
        '/api/form-from-archive', json={'data': _logbook(), 'mode': 'recipe'}
    )
    assert response.json()['system'] == 'LA-PLD'
    response = client.post('/api/form-from-archive', json={'data': {'m_def': 'x.Y'}})
    assert response.status_code == HTTP_BAD_REQUEST
