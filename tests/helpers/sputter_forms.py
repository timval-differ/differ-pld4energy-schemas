"""Complete sputter_logbook dashboard forms and builders shared by the tests."""

import copy

from differ_pld4e_schemas.dashboards.sputter_logbook.convert import form_to_files
from differ_pld4e_schemas.dashboards.sputter_logbook.spec import form_spec

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
