"""Complete pld_logbook dashboard forms and builders shared by the tests."""

import copy

from differ_pld4e_schemas.dashboards.pld_logbook.convert import form_to_files
from differ_pld4e_schemas.dashboards.pld_logbook.spec import form_spec

SPEC = form_spec()
TARGET = '../uploads/target_db/archive/target1#/data'
OTHER_TARGET = '../uploads/target_db/archive/target2#/data'
EXISTING = '../uploads/u0/archive/sample0#/data'
SI_WAFER = '../uploads/target_db/archive/substrate_si#/data'
EXPECTED_T1 = 0.42 / 0.5 / 0.92 * 100
EXPECTED_PULSES = 3000
PULSES = 1500
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
    'target_select': 0,
    'target_scan_axis': 'X',
    'target_area': 'Square filled',
    'scan_width_x': 10,
    'scan_width_y': 8,
    'spot_width': 1,
    'spot_height': 1,
    'scan_speed_x': 2,
    'scan_speed_y': 1.5,
    'target_size': '25mm / 1"',
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

# Values for both systems; the browser only sends those of the chosen system,
# the others are hidden and ignored.
HEATER_CONTROL = {
    'heating_mode': 'Laser heating (PID)',
    'laser_output_limitation': 50,
    'fix_output': False,
    'drift_compensation': True,
    'supply_voltage': 20,
    'supply_current': 5,
    'actual_voltage': 19.8,
    'actual_current': 4.9,
}

DEPOSITION = {
    'uid': 'step2',
    'type': 'deposition',
    'start_time': '10:10',
    'end_time': '10:40',
    'sample': 'new:sub1',
    'target': TARGET,
    'film_thickness_unit': 'nm',
    'film_thickness': 20,
    **HEATER_CONTROL,
    'x': 1,
    'y': 2,
    'z': 50,
    'tilt': 0,
    'spin': 0,
    'heater_scan_type': 'Polar scan',
    'heater_scan_axis': 'X',
    'heater_size': '25mm / 1"',
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
            'start_time': '09:20',
            'end_time': '10:05',
            **HEATER_CONTROL,
            'ramp_on': True,
            'ramp_rate': 10,
            'temperature_setpoint': 700,
            'heater_output': 35,
            'pressure': 0.1,
            **GAS_O2,
        },
        DEPOSITION,
    ],
    'in_situ': [
        {
            'uid': 'm1',
            'sample': 'new:sub1',
            'steps': ['step2'],
            'rheed': True,
            'rheed_pattern_export_files': [
                'pld_files/run1/in_situ_1/pattern1.png',
                'pld_files/run1/in_situ_1/pattern2.png',
            ],
            'la_eds': True,
            'la_eds_sp0_files': ['pld_files/run1/in_situ_1/spectrum.sp0'],
            'la_eds_energy_offset': 100,
            'la_eds_energy_per_channel': 10,
        }
    ],
    'logfiles': {'system_logfiles': ['pld_files/run1/logfiles/tsst.txt']},
}

ANNEALING = {
    'uid': 'anneal',
    'type': 'annealing',
    'start_time': '09:30',
    'end_time': '10:00',
    'atmosphere': 'UHV',
    **HEATER_CONTROL,
    'heating_mode': 'Laser heating (power)',
    'power_setpoint': 40,
    'power_ramp_rate': 5,
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
    data['in_situ'] = []
    return data


def messages(errors):
    return {error['path']: error['message'] for error in errors}


def _sections():
    return {s['key']: s for s in SPEC['sections']}


def _logbook(data=None):
    return form_to_files(data or FORM, SPEC)['files'][-1]['archive']['data']
