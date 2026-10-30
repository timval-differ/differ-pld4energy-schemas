"""
Declarative definition of the PLD logbook form.

The same definition drives the browser form (rendering, live validation and
conditional fields) and the server (validation and conversion to an archive), so
both always agree on what is required. Field keys are described in
`dashboards.common.fields`.

Section keys, besides those of the fields:
    requirement  {'from_steps': aspect}: how much of the section is needed
                 follows the process steps, see `rules.section_requirement`
    count_control  the list offers a "how many" input (samples)

Step variant keys:
    laser        'required' | 'optional' | 'none': whether the step needs the
                 laser (and so the laser details and targets). An optional step
                 gets a "Laser used" toggle in front of its laser fields.
    prefill_from variant whose values a new step of this variant starts with,
                 taken from the last such step (e.g. deposition after
                 pre-ablation)
"""

from __future__ import annotations

# Importing the schema package fixes the package name that qualified section
# names (the m_def written into archive files) are built from.
import differ_pld4e_schemas.schema_packages.schema_package  # noqa: F401
from differ_pld4e_schemas.gas import ATMOSPHERES as GAS_ATMOSPHERES
from differ_pld4e_schemas.gas import BACKGROUND_GAS, GASES
from differ_pld4e_schemas.in_situ import InSituTechniquesEntry
from differ_pld4e_schemas.laser import (
    LASER_CALIBRATION_INSTRUCTIONS,
    LASER_MODES,
    MAGNIFICATIONS,
    MASK_SIZES,
)
from differ_pld4e_schemas.pld_deposition import (
    CARRIERS,
    CARTESIAN_SCAN,
    POLAR_SCAN,
    TARGET_NUMBERS,
    LAPLDLogbook,
    SAPLDLogbook,
)
from differ_pld4e_schemas.sample import Sample, SubstrateType
from differ_pld4e_schemas.target import PLDTarget

from ..common.fields import comments, field, number
from ..common.samples import sample_section

SYSTEMS = ('SA-PLD', 'LA-PLD')
LOGBOOK_SECTIONS = {'SA-PLD': SAPLDLogbook, 'LA-PLD': LAPLDLogbook}
ATMOSPHERES = list(GAS_ATMOSPHERES)
LASER_LEVELS = ('none', 'optional', 'required')

SA = {'key': '/run/system', 'equals': 'SA-PLD'}
LA = {'key': '/run/system', 'equals': 'LA-PLD'}
LASER_STEPS = {'from_steps': 'laser'}


def gas_fields():
    group = 'Background gases'
    in_gas = {'key': 'atmosphere', 'equals': BACKGROUND_GAS}
    fields = [
        field(
            'atmosphere',
            'Atmosphere',
            'select',
            options=ATMOSPHERES,
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
            unit_label='%',
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


def laser_fields():
    group = 'Laser'
    return [
        field(
            'laser_mode',
            'Laser mode',
            'select',
            options=list(LASER_MODES),
            archive='laser.laser_mode',
            group=group,
        ),
        number(
            'laser_voltage',
            'Laser voltage',
            'kV',
            archive='laser.laser_voltage',
            group=group,
        ),
        field(
            'magnification',
            'Magnification',
            'select',
            options=list(MAGNIFICATIONS),
            archive='laser.magnification',
            group=group,
        ),
        field(
            'mask_size',
            'Mask size',
            'select',
            options=list(MASK_SIZES),
            archive='laser.mask_size',
            group=group,
        ),
        number(
            'spot_size',
            'Spot size',
            'mm^2',
            unit_label='mm²',
            archive='laser.spot_size',
            group=group,
        ),
        number(
            'laser_fluence',
            'Laser fluence',
            'J/cm^2',
            unit_label='J/cm²',
            archive='laser.laser_fluence',
            group=group,
        ),
        number(
            'laser_energy',
            'Laser energy',
            'mJ',
            archive='laser.laser_energy',
            group=group,
        ),
        number(
            'attenuator_position',
            'Attenuator position',
            unit_label='%',
            archive='laser.attenuator_position',
            group=group,
        ),
        number(
            'laser_frequency',
            'Laser frequency',
            'Hz',
            archive='laser.laser_frequency',
            group=group,
        ),
        field(
            'number_of_laser_pulses',
            'Number of laser pulses',
            'integer',
            min=1,
            archive='laser.number_of_laser_pulses',
            group=group,
        ),
    ]


def target_stage_fields():
    group = 'Target stage'
    return [
        number(key, label, unit, archive=f'target_stage.{key}', group=group)
        for key, label, unit in (
            ('start_x_position', 'Start x-position', 'mm'),
            ('x_offset', 'x-offset', 'mm'),
            ('start_y_position', 'Start y-position', 'mm'),
            ('y_offset', 'y-offset', 'mm'),
            ('start_z_position', 'Start z-position', 'mm'),
            ('scan_width_x', 'Scan width x', 'mm'),
            ('scan_width_y', 'Scan width y', 'mm'),
            ('scan_speed_x', 'Scan speed x', 'mm/s'),
            ('scan_speed_y', 'Scan speed y', 'mm/s'),
        )
    ]


def heater_stage_fields():
    group = 'Heater stage position'
    return [
        number(
            key,
            key,
            unit,
            unit_label=label,
            archive=f'heater_stage_position.{key}',
            group=group,
        )
        for key, unit, label in (
            ('x', 'mm', None),
            ('y', 'mm', None),
            ('z', 'mm', None),
            ('tilt', 'degree', '°'),
            ('spin', 'degree', '°'),
        )
    ]


def substrate_scan_fields(visible_if):
    """Substrate stage scan of the SA-PLD."""
    return [
        number(
            f'substrate_{key}',
            label,
            unit,
            archive=f'substrate_scan.{key}',
            visible_if=visible_if,
            group='Substrate stage scan',
        )
        for key, label, unit in (
            ('scan_width_x', 'Scan width x', 'mm'),
            ('scan_width_y', 'Scan width y', 'mm'),
            ('scan_speed_x', 'Scan speed x', 'mm/s'),
            ('scan_speed_y', 'Scan speed y', 'mm/s'),
        )
    ]


def cartesian_scan_fields(visible_if):
    """Cartesian heater stage scan of the LA-PLD."""
    return [
        number(
            f'cartesian_{key}',
            label,
            unit,
            archive=f'cartesian_scan.{archive}',
            visible_if=visible_if,
            group='Cartesian scan',
        )
        for key, archive, label, unit in (
            ('x_offset', 'x_offset', 'x-offset', 'mm'),
            ('y_offset', 'y_offset', 'y-offset', 'mm'),
            ('scan_rate', 'scan_rate', 'Scan rate', 'mm/s'),
            ('rotation_rate', 'rotation_rate', 'Rotation rate', 'rpm'),
        )
    ]


def polar_scan_fields(visible_if):
    group = 'Polar scan'
    return [
        *[
            number(
                key,
                label,
                unit,
                archive=f'polar_scan.{key}',
                visible_if=visible_if,
                group=group,
            )
            for key, label, unit in (
                ('radius_start', 'Radius start', 'mm'),
                ('radius_stop', 'Radius stop', 'mm'),
                ('pulse_spacing', 'Pulse spacing', 'mm'),
                ('max_laser_frequency', 'Max laser frequency', 'Hz'),
            )
        ],
        field(
            'number_of_scans',
            'Number of scans',
            'integer',
            min=1,
            archive='polar_scan.number_of_scans',
            visible_if=visible_if,
            group=group,
        ),
    ]


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


def variant(label, sections, fields, laser='none', laser_keys=(), **kwargs):
    """
    A step variant. For an optional laser, the fields named in
    `laser_keys` only show (and are only required) once "Laser used" is
    ticked.
    """
    if laser not in LASER_LEVELS:
        raise ValueError(f'Unknown laser level {laser}')
    if laser == 'optional':
        used = {'key': 'laser_used', 'equals': True}
        fields = [
            field('laser_used', 'Laser used', 'bool', archive=None),
            *[
                dict(
                    f,
                    visible_if={'all': [used, f['visible_if']]}
                    if f.get('visible_if')
                    else used,
                )
                if f['key'] in laser_keys
                else f
                for f in fields
            ],
        ]
    return {
        'label': label,
        'sections': sections,
        'fields': fields,
        'laser': laser,
        **kwargs,
    }


def _sections(name):
    return {'SA-PLD': f'SAPLD{name}', 'LA-PLD': f'LAPLD{name}'}


def step_variants():
    target = field('target', 'Target', 'target_choice')
    pre_ablation = [
        field(
            'laser_mode',
            'Laser mode',
            'select',
            options=list(LASER_MODES),
            archive='laser.laser_mode',
        ),
        number('laser_voltage', 'Laser voltage', 'kV', archive='laser.laser_voltage'),
        target,
        *target_stage_fields(),
        temperature('substrate_temperature', 'Substrate temperature'),
        pressure('Pre-ablation pressure'),
        *gas_fields(),
        *[f for f in laser_fields() if f['key'] not in ('laser_mode', 'laser_voltage')],
        comments(),
    ]
    scan_on = {'key': 'substrate_stage_scan', 'equals': True}
    polar = {'all': [LA, {'key': 'heater_scan_type', 'equals': POLAR_SCAN}]}
    cartesian = {'all': [LA, {'key': 'heater_scan_type', 'equals': CARTESIAN_SCAN}]}
    deposition = [
        field(
            'sample',
            'Sample',
            'sample_choice',
            archive=None,
            visible_if=LA,
        ),
        target,
        number(
            'film_thickness',
            'Film thickness',
            'nm',
            help='The film grown in this step; together with the target it makes '
            'up the sample name.',
        ),
        *heater_stage_fields(),
        field(
            'substrate_stage_scan',
            'Substrate stage scan',
            'bool',
            visible_if=SA,
            group='Substrate stage scan',
        ),
        *substrate_scan_fields({'all': [SA, scan_on]}),
        field(
            'heater_scan_type',
            'Heater scan type',
            'select',
            options=[POLAR_SCAN, CARTESIAN_SCAN],
            default=POLAR_SCAN,
            visible_if=LA,
            group='Heater stage scan',
        ),
        *polar_scan_fields(polar),
        *cartesian_scan_fields(cartesian),
        *target_stage_fields(),
        temperature('substrate_temperature', 'Substrate temperature'),
        pressure('Deposition pressure'),
        *gas_fields(),
        *laser_fields(),
        comments(),
    ]

    def ramp(label, *extra):
        return [
            *gas_fields(),
            number('ramp_rate', 'Ramp rate', 'K/minute', unit_label='°C/min'),
            temperature('temperature_setpoint', 'Temperature setpoint'),
            *extra,
            pressure(label),
            comments(),
        ]

    annealing = [
        *gas_fields(),
        temperature('temperature_setpoint', 'Temperature setpoint'),
        heater_output(),
        number('dwell_time', 'Dwell time', 'minute', unit_label='min'),
        pressure('Annealing pressure'),
        comments(),
    ]

    return {
        'pre_ablation': variant(
            'Pre-ablation step',
            _sections('PreAblationStep'),
            pre_ablation,
            laser='required',
        ),
        'heating': variant(
            'Heating step',
            _sections('HeatingStep'),
            ramp('Heating pressure', heater_output()),
        ),
        'annealing': variant('Annealing step', _sections('AnnealingStep'), annealing),
        'deposition': variant(
            'Pulsed laser deposition step',
            _sections('DepositionStep'),
            deposition,
            laser='required',
            prefill_from='pre_ablation',
        ),
        'cool_down': variant(
            'Cool-down step',
            _sections('CoolDownStep'),
            ramp('Cool-down pressure'),
        ),
    }


IN_SITU_TECHNIQUES = {
    'rheed': (
        'RHEED (KSA 400)',
        [
            ('pattern_native_file', 'Pattern capture, native (.img)', '.img'),
            ('pattern_export_file', 'Pattern capture, exported (.png)', '.png'),
            ('roi_intensity_native_file', 'ROI intensity map, native (.kdt)', '.kdt'),
            ('roi_intensity_export_file', 'ROI intensity map, exported (.txt)', '.txt'),
        ],
    ),
    'mic': (
        'MIC (EZ-Curve)',
        [
            ('native_file', 'Native file (.ezc)', '.ezc'),
            ('export_file', 'Exported file (.csv)', '.csv'),
        ],
    ),
    'se': ('SE', [('file', 'Data file', '')]),
    'la_eds': ('LA-EDS (RSX1000)', [('sp0_file', 'Spectrum (.sp0)', '.sp0')]),
    'oes': ('OES', [('file', 'Data file', '')]),
    'shg': ('SHG', [('file', 'Data file', '')]),
}


def in_situ_fields():
    """
    Data files are optional: they are often collected from other computers
    after the run, and a technique without files is marked as awaiting data.
    """
    fields = []
    for technique, (label, files) in IN_SITU_TECHNIQUES.items():
        on = {'key': technique, 'equals': True}
        fields.append(
            field(technique, f'{label} used', 'bool', archive=None, group=label)
        )
        for name, file_label, accept in files:
            fields.append(
                field(
                    f'{technique}_{name}',
                    file_label,
                    'file',
                    accept=accept,
                    required=False,
                    archive=f'{technique}.{name}',
                    visible_if=on,
                    group=label,
                    technique=technique,
                )
            )
        if technique == 'la_eds':
            fields += [
                number(
                    'la_eds_energy_offset',
                    'Energy offset E0',
                    'eV',
                    required=False,
                    archive='la_eds.energy_offset',
                    visible_if=on,
                    group=label,
                ),
                number(
                    'la_eds_energy_per_channel',
                    'Energy per channel',
                    'eV',
                    required=False,
                    archive='la_eds.energy_per_channel',
                    visible_if=on,
                    group=label,
                ),
            ]
        fields.append(
            field(
                f'{technique}_comments',
                'Comments',
                'textarea',
                archive=f'{technique}.comments',
                visible_if=on,
                group=label,
            )
        )
    return fields


def form_spec() -> dict:
    """The complete form definition, as sent to the browser."""
    return {
        'systems': list(SYSTEMS),
        'logbook_sections': {
            system: section.m_def.qualified_name()
            for system, section in LOGBOOK_SECTIONS.items()
        },
        'reference_sections': {
            'target': PLDTarget.m_def.qualified_name(),
            'sample': Sample.m_def.qualified_name(),
            'substrate': SubstrateType.m_def.qualified_name(),
            'in_situ': InSituTechniquesEntry.m_def.qualified_name(),
        },
        'sections': [
            {
                'key': 'run',
                'title': 'Run',
                'kind': 'object',
                'intro': (
                    'Who does the run, in which system and when. The system, date '
                    'and time make up the sample IDs.'
                ),
                'fields': [
                    field('operator_name', 'Name'),
                    field('operator_email', 'Email'),
                    field(
                        'system',
                        'PVD system',
                        'select',
                        options=list(SYSTEMS),
                        archive=None,
                    ),
                    field('date', 'Date', 'date', archive=None),
                    field('time', 'Start time', 'time', archive=None),
                    field(
                        'name',
                        'Run name',
                        placeholder='optional, e.g. SrTiO3 on Si',
                        required=False,
                    ),
                ],
            },
            sample_section(),
            {
                'key': 'chamber',
                'title': 'System details',
                'kind': 'object',
                'fields': [
                    field(
                        'substrate_carrier',
                        'Substrate carrier',
                        'select',
                        options_by={
                            'key': '/run/system',
                            'map': {k: list(v) for k, v in CARRIERS.items()},
                            'empty_text': 'Choose the PVD system first',
                        },
                    ),
                    number('base_pressure', 'Base pressure main chamber', 'mbar'),
                    field(
                        'particle_reduction_plate',
                        'Particle reduction plate',
                        'select',
                        options=['in use', 'not in use'],
                        visible_if=LA,
                    ),
                    comments(),
                ],
            },
            {
                'key': 'targets',
                'title': 'Targets',
                'kind': 'list',
                'item_label': 'Target',
                'min_items': 1,
                'requirement': LASER_STEPS,
                'unique': ['target', 'target_number'],
                'fields': [
                    field(
                        'target',
                        'Target',
                        'reference',
                        reference='target',
                        # The material names the films of the samples.
                        ref_copy={'material': 'material'},
                        archive=None,
                    ),
                    field(
                        'target_number',
                        'Target number',
                        'select',
                        options=[str(number) for number in TARGET_NUMBERS],
                    ),
                ],
            },
            {
                'key': 'laser',
                'title': 'Laser details',
                'kind': 'object',
                'intro': LASER_CALIBRATION_INSTRUCTIONS,
                'requirement': LASER_STEPS,
                'fields': [
                    number(
                        'energy_before_chamber', 'Laser energy before chamber', 'mJ'
                    ),
                    number('energy_after_chamber', 'Laser energy after chamber', 'mJ'),
                    number(
                        'transmission_window_2',
                        'Transmission 2nd window',
                        unit_label='%',
                        default=92,
                    ),
                    field(
                        'transmission_window_1_manual',
                        'Enter the 1st window transmission manually',
                        'bool',
                    ),
                    field(
                        'transmission_window_1_calculated',
                        'Transmission 1st window = E_after / (E_before × T2)',
                        'computed',
                        compute='transmission_window_1',
                        unit_label='%',
                        archive=None,
                        visible_if={
                            'key': 'transmission_window_1_manual',
                            'equals': False,
                        },
                    ),
                    number(
                        'transmission_window_1',
                        'Transmission 1st window',
                        unit_label='%',
                        visible_if={
                            'key': 'transmission_window_1_manual',
                            'equals': True,
                        },
                    ),
                    comments(archive='comments'),
                ],
            },
            {
                'key': 'steps',
                'title': 'Process steps',
                'kind': 'variant_list',
                'item_label': 'Step',
                'variants': step_variants(),
            },
            {
                'key': 'in_situ',
                'title': 'In-situ techniques',
                'kind': 'object',
                'intro': (
                    'Tick the techniques you used. Their data files can be added '
                    'now or later, e.g. once they are collected from the other '
                    'computers: open the saved logbook and add them.'
                ),
                'fields': in_situ_fields(),
            },
        ],
    }
