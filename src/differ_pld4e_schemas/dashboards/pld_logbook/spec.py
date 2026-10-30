"""
Declarative definition of the PLD logbook form.

The same definition drives the browser form (rendering, live validation and
conditional fields) and the server (validation and conversion to an archive), so
both always agree on what is required.

Field keys:
    key          key in the form data of the containing section or list item
    label        label shown in the form
    kind         text | textarea | number | integer | select | bool | date |
                 reference | target_choice | substrate_choice | file | computed
    unit         pint unit the user enters the value in (converted to the
                 schema's SI unit when the archive is built)
    unit_label   how the unit is shown, if different from `unit`
    archive      dotted path of the quantity in the archive section, relative to
                 the section the containing object maps to; None if the value is
                 handled by the converter itself
    required     whether the value must be filled in while the field is visible
    visible_if   condition, see `rules.evaluate`
    options      choices of a select, or `options_by` for choices that depend on
                 another field
    group        heading the field is shown under
"""

from __future__ import annotations

# Importing the schema package fixes the package name that qualified section
# names (the m_def written into archive files) are built from.
import differ_pld4e_schemas.schema_packages.schema_package  # noqa: F401
from differ_pld4e_schemas.in_situ import InSituTechniquesEntry
from differ_pld4e_schemas.pld_deposition import LAPLDLogbook, SAPLDLogbook
from differ_pld4e_schemas.pld_substrate import PLDSubstrate
from differ_pld4e_schemas.target import PLDTarget

SYSTEMS = ('SA-PLD', 'LA-PLD')
LOGBOOK_SECTIONS = {'SA-PLD': SAPLDLogbook, 'LA-PLD': LAPLDLogbook}

CARRIERS = {
    'SA-PLD': ['Omicron carrier', '1" carrier'],
    'LA-PLD': [
        'Omicron carrier',
        '1" carrier',
        '4" wafer carrier',
        'Sample select carrier',
    ],
}
SUBSTRATE_MATERIALS = ['Si', 'SrTiO3 (001)', 'glass', 'F:TiO2']
GASES = ['Ar', 'O2', 'N2']
LASER_MODES = ['HV NGR', 'HV PGR', 'EGY PGR', 'EGY NGR']
MAGNIFICATIONS = ['5X', '10X']
MASK_SIZES = ['3x12', '4x12', '3x15', '4x15', '4x2 (5 slits)']
POLAR_SCAN = 'Polar scan'
CARTESIAN_SCAN = 'Cartesian scan'

LASER_INSTRUCTIONS = (
    'Set the attenuator position 100% open, laser frequency 1 Hz, HV NGR mode '
    'with HV = 22 kV, Energy = 500 mJ. Mask size of 5x18 mm.'
)

SA = {'key': '/run/system', 'equals': 'SA-PLD'}
LA = {'key': '/run/system', 'equals': 'LA-PLD'}


def field(key, label, kind='text', **kwargs):
    kwargs.setdefault('required', kind not in ('textarea', 'bool', 'computed'))
    kwargs.setdefault('archive', key)
    return {'key': key, 'label': label, 'kind': kind, **kwargs}


def number(key, label, unit=None, **kwargs):
    return field(key, label, 'number', unit=unit, **kwargs)


def comments(**kwargs):
    kwargs.setdefault('archive', 'description')
    return field('comments', 'Comments', 'textarea', **kwargs)


def gas_fields():
    fields = []
    for gas in GASES:
        on = {'key': f'gas_{gas}', 'equals': True}
        group = 'Background gases'
        fields += [
            field(
                f'gas_{gas}',
                gas,
                'bool',
                archive=None,
                group=group,
                gas=gas,
                row_start=True,
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
            number(
                f'gas_{gas}_valve_position',
                f'{gas} valve position',
                unit_label='%',
                archive='valve_position',
                visible_if=on,
                group=group,
                gas=gas,
            ),
            field(
                f'gas_{gas}_valve_position_fixed',
                f'{gas} valve position fixed',
                'bool',
                archive='valve_position_fixed',
                visible_if=on,
                group=group,
                gas=gas,
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
            options=LASER_MODES,
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
            options=MAGNIFICATIONS,
            archive='laser.magnification',
            group=group,
        ),
        field(
            'mask_size',
            'Mask size',
            'select',
            options=MASK_SIZES,
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


def target_stage_fields(**kwargs):
    group = 'Target stage'
    return [
        number(key, label, 'mm', archive=f'target_stage.{key}', group=group, **kwargs)
        for key, label in (
            ('start_x_position', 'Start x-position'),
            ('x_offset', 'x-offset'),
            ('start_y_position', 'Start y-position'),
            ('y_offset', 'y-offset'),
            ('scan_area', 'Scan area'),
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


def cartesian_scan_fields(visible_if):
    group = 'Cartesian scan'
    return [
        number(
            'cartesian_x_offset',
            'x-offset',
            'mm',
            archive='cartesian_scan.x_offset',
            visible_if=visible_if,
            group=group,
        ),
        number(
            'cartesian_y_offset',
            'y-offset',
            'mm',
            archive='cartesian_scan.y_offset',
            visible_if=visible_if,
            group=group,
        ),
        number(
            'cartesian_scan_rate',
            'Scan rate',
            'mm/s',
            archive='cartesian_scan.scan_rate',
            visible_if=visible_if,
            group=group,
        ),
        number(
            'cartesian_rotation_rate',
            'Rotation rate',
            'rpm',
            archive='cartesian_scan.rotation_rate',
            visible_if=visible_if,
            group=group,
        ),
    ]


def polar_scan_fields(visible_if):
    group = 'Polar scan'
    return [
        number(
            'radius_start',
            'Radius start',
            'mm',
            archive='polar_scan.radius_start',
            visible_if=visible_if,
            group=group,
        ),
        number(
            'radius_stop',
            'Radius stop',
            'mm',
            archive='polar_scan.radius_stop',
            visible_if=visible_if,
            group=group,
        ),
        number(
            'pulse_spacing',
            'Pulse spacing',
            'mm',
            archive='polar_scan.pulse_spacing',
            visible_if=visible_if,
            group=group,
        ),
        number(
            'max_laser_frequency',
            'Max laser frequency',
            'Hz',
            archive='polar_scan.max_laser_frequency',
            visible_if=visible_if,
            group=group,
        ),
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


def step_variants():
    target = field('target', 'Target', 'target_choice')
    pre_ablation = [
        field(
            'laser_mode',
            'Laser mode',
            'select',
            options=LASER_MODES,
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
    cartesian = {
        'any': [
            {'all': [SA, scan_on]},
            {'all': [LA, {'key': 'heater_scan_type', 'equals': CARTESIAN_SCAN}]},
        ]
    }
    deposition = [
        field('substrate', 'Substrate', 'substrate_choice'),
        target,
        *heater_stage_fields(),
        field(
            'substrate_stage_scan',
            'Substrate stage scan',
            'bool',
            visible_if=SA,
            group='Heater stage scan',
        ),
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

    def ramp(label):
        return [
            *gas_fields(),
            number('ramp_rate', 'Ramp rate', 'K/minute', unit_label='°C/min'),
            temperature('temperature_setpoint', 'Temperature setpoint'),
            pressure(label),
            comments(),
        ]

    return {
        'pre_ablation': {
            'label': 'Pre-ablation step',
            'sections': {
                'SA-PLD': 'SAPLDPreAblationStep',
                'LA-PLD': 'LAPLDPreAblationStep',
            },
            'fields': pre_ablation,
        },
        'heating': {
            'label': 'Heating step',
            'sections': {'SA-PLD': 'SAPLDHeatingStep', 'LA-PLD': 'LAPLDHeatingStep'},
            'fields': ramp('Heating pressure'),
        },
        'deposition': {
            'label': 'Pulsed laser deposition step',
            'sections': {
                'SA-PLD': 'SAPLDDepositionStep',
                'LA-PLD': 'LAPLDDepositionStep',
            },
            'fields': deposition,
        },
        'cool_down': {
            'label': 'Cool-down step',
            'sections': {'SA-PLD': 'SAPLDCoolDownStep', 'LA-PLD': 'LAPLDCoolDownStep'},
            'fields': ramp('Cool-down pressure'),
        },
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
    fields, rules = [], []
    for technique, (label, files) in IN_SITU_TECHNIQUES.items():
        on = {'key': technique, 'equals': True}
        fields.append(
            field(technique, f'{label} used', 'bool', archive=None, group=label)
        )
        keys = []
        for name, file_label, accept in files:
            key = f'{technique}_{name}'
            keys.append(key)
            fields.append(
                field(
                    key,
                    file_label,
                    'file',
                    accept=accept,
                    required=False,
                    archive=f'{technique}.{name}',
                    visible_if=on,
                    group=label,
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
        rules.append(
            {
                'type': 'any_of',
                'keys': keys,
                'visible_if': on,
                'message': f'Add at least one {label.split(" ")[0]} file.',
            }
        )
    return fields, rules


def form_spec() -> dict:
    """The complete form definition, as sent to the browser."""
    in_situ, in_situ_rules = in_situ_fields()
    return {
        'systems': list(SYSTEMS),
        'logbook_sections': {
            system: section.m_def.qualified_name()
            for system, section in LOGBOOK_SECTIONS.items()
        },
        'reference_sections': {
            'target': PLDTarget.m_def.qualified_name(),
            'substrate': PLDSubstrate.m_def.qualified_name(),
            'in_situ': InSituTechniquesEntry.m_def.qualified_name(),
        },
        'sections': [
            {
                'key': 'run',
                'title': 'System details',
                'kind': 'object',
                'fields': [
                    field(
                        'system',
                        'PVD system',
                        'select',
                        options=list(SYSTEMS),
                        archive=None,
                    ),
                    field(
                        'name',
                        'Run name',
                        placeholder='e.g. SrTiO3 on Si',
                        archive='name',
                    ),
                    field('date', 'Date', 'date', archive=None),
                    number('base_pressure', 'System base pressure', 'mbar'),
                    field(
                        'substrate_carrier',
                        'Substrate carrier',
                        'select',
                        options_by={'key': '/run/system', 'map': CARRIERS},
                    ),
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
                'key': 'laser',
                'title': 'Laser details',
                'kind': 'object',
                'intro': LASER_INSTRUCTIONS,
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
                'key': 'targets',
                'title': 'Targets',
                'kind': 'list',
                'item_label': 'Target',
                'min_items': 1,
                'unique': ['target', 'target_number'],
                'fields': [
                    field(
                        'target',
                        'Target',
                        'reference',
                        reference='target',
                        archive=None,
                    ),
                    field('target_number', 'Target number', 'integer', min=1),
                ],
            },
            {
                'key': 'substrates',
                'title': 'Substrates',
                'kind': 'list',
                'item_label': 'Substrate',
                'min_items': 1,
                'unique': ['sample_user_id', 'substrate'],
                'fields': [
                    field(
                        'mode',
                        'Substrate',
                        'select',
                        options=['Create new substrate', 'Use existing substrate'],
                        default='Create new substrate',
                        archive=None,
                    ),
                    field(
                        'substrate',
                        'Existing substrate',
                        'reference',
                        reference='substrate',
                        archive=None,
                        visible_if={'key': 'mode', 'equals': 'Use existing substrate'},
                    ),
                    *[
                        dict(
                            f,
                            visible_if={
                                'key': 'mode',
                                'equals': 'Create new substrate',
                            },
                        )
                        for f in (
                            field(
                                'sample_name',
                                'Sample name',
                                placeholder='Substrate_ThinFilm-thickness_next_layer',
                            ),
                            field('run_number', 'Run number'),
                            field('sample_number', 'Sample number'),
                            field(
                                'sample_user_id',
                                'Sample user ID',
                                'computed',
                                compute='sample_user_id',
                                archive=None,
                            ),
                            field(
                                'size', 'Substrate size', placeholder='e.g. 10x10 mm'
                            ),
                            field(
                                'substrate_material',
                                'Substrate material',
                                'select',
                                options=SUBSTRATE_MATERIALS,
                            ),
                            comments(archive='comments'),
                        )
                    ],
                ],
            },
            {
                'key': 'steps',
                'title': 'Process steps',
                'kind': 'variant_list',
                'item_label': 'Step',
                'min_items': 1,
                'required_variants': ['deposition'],
                'variants': step_variants(),
            },
            {
                'key': 'in_situ',
                'title': 'In-situ techniques',
                'kind': 'object',
                'intro': 'Tick the techniques you used and add their files.',
                'fields': in_situ,
                'rules': in_situ_rules,
            },
        ],
    }
