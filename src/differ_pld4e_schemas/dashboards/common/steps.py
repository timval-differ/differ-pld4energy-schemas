"""
Field groups of the process steps that every PVD system has: the background
gases, pressure and temperatures. They map to `process_steps.GasProcessStep`
and its heating and cool-down steps.
"""

from __future__ import annotations

from differ_pld4e_schemas.gas import ATMOSPHERES, BACKGROUND_GAS, GASES
from differ_pld4e_schemas.process_steps import VALVE_POSITION_MAX

from .fields import comments, field, number


def gas_fields():
    group = 'Background gases'
    in_gas = {'key': 'atmosphere', 'equals': BACKGROUND_GAS}
    fields = [
        field(
            'atmosphere',
            'Atmosphere',
            'select',
            options=list(ATMOSPHERES),
            default=BACKGROUND_GAS,
            group=group,
        )
    ]
    for gas in GASES:
        on = {'all': [in_gas, {'key': f'gas_{gas}', 'equals': True}]}
        fields += [
            field(
                f'gas_{gas}',
                gas,
                'bool',
                archive=None,
                group=group,
                gas=gas,
                row_start=True,
                visible_if=in_gas,
            ),
            number(
                f'gas_{gas}_flow_setpoint',
                f'{gas} set flow',
                'cm^3/minute',
                unit_label='sccm',
                archive='flow_setpoint',
                visible_if=on,
                group=group,
                gas=gas,
            ),
            number(
                f'gas_{gas}_flow_readout',
                f'{gas} read-out flow',
                'cm^3/minute',
                unit_label='sccm',
                archive='flow_readout',
                visible_if=on,
                group=group,
                gas=gas,
            ),
        ]
    # One valve for all gases.
    any_gas = {
        'all': [
            in_gas,
            {'any': [{'key': f'gas_{gas}', 'equals': True} for gas in GASES]},
        ]
    }
    fields += [
        number(
            'valve_position',
            'Valve position',
            min=0,
            max=VALVE_POSITION_MAX,
            help=f'0 (closed) to {VALVE_POSITION_MAX} (open).',
            visible_if=any_gas,
            group=group,
            row_start=True,
        ),
        field(
            'valve_position_fixed',
            'Valve position fixed',
            'bool',
            visible_if=any_gas,
            group=group,
        ),
    ]
    return fields


def temperature(key, label, **kwargs):
    return number(key, label, 'degC', unit_label='°C', **kwargs)


def pressure(label):
    return number('pressure', label, 'mbar')


def heater_output():
    return number(
        'heater_output',
        'Heater output once the setpoint is reached',
        unit_label='%',
    )


def ramp_fields(label, *extra):
    """A heating or cool-down step."""
    return [
        *gas_fields(),
        number('ramp_rate', 'Ramp rate', 'K/minute', unit_label='°C/min'),
        temperature('temperature_setpoint', 'Temperature setpoint'),
        *extra,
        pressure(label),
        comments(),
    ]
