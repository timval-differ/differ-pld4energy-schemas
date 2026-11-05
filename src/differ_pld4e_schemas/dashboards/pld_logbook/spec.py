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
from differ_pld4e_schemas.stages import SCAN_AREAS, SCAN_AXES, SCAN_SIZES
from differ_pld4e_schemas.target import PLDTarget

from ..common.fields import comments, field, number
from ..common.samples import sample_section
from ..common.steps import (
    gas_fields,
    heater_output,
    pressure,
    ramp_fields,
    temperature,
)
from .rules import ALL_SAMPLES, FILM_STEPS

DRAFT_DIR = 'pld_drafts'
SYSTEMS = ('SA-PLD', 'LA-PLD')
LOGBOOK_SECTIONS = {'SA-PLD': SAPLDLogbook, 'LA-PLD': LAPLDLogbook}
LASER_LEVELS = ('none', 'optional', 'required')

SA = {'key': '/run/system', 'equals': 'SA-PLD'}
LA = {'key': '/run/system', 'equals': 'LA-PLD'}
LASER_STEPS = {'from_steps': 'laser'}


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


def select(key, label, options, default=None, **kwargs):
    return field(
        key,
        label,
        'select',
        options=list(options),
        default=default or options[0],
        **kwargs,
    )


# Position and scan fields follow the "Manual movement" and "Define scan
# pattern" dialogs of the system software.


def target_stage_fields():
    group = 'Target stage'

    def stage(key, label, unit, **kwargs):
        return number(
            key, label, unit, archive=f'target_stage.{key}', group=group, **kwargs
        )

    return [
        stage('start_x_position', 'Target x', 'mm'),
        stage('start_y_position', 'Target y', 'mm'),
        stage('start_z_position', 'Target z', 'mm'),
        stage('target_select', 'Target select', 'degree', unit_label='deg.'),
        select(
            'target_scan_axis',
            'Scan axis',
            SCAN_AXES,
            archive='target_stage.scan_axis',
            group=group,
        ),
        select(
            'target_area',
            'Area',
            SCAN_AREAS,
            default='Square filled',
            archive='target_stage.area',
            group=group,
        ),
        *[
            stage(key, label, unit)
            for key, label, unit in (
                ('scan_width_x', 'Width X', 'mm'),
                ('scan_width_y', 'Height Y', 'mm'),
                ('spot_width', 'Spot width', 'mm'),
                ('spot_height', 'Spot height', 'mm'),
                ('x_offset', 'Offset X', 'mm'),
                ('y_offset', 'Offset Y', 'mm'),
                ('scan_speed_x', 'Scan speed X', 'mm/s'),
                ('scan_speed_y', 'Scan speed Y', 'mm/s'),
            )
        ],
        select(
            'target_size',
            'Target size',
            SCAN_SIZES,
            archive='target_stage.target_size',
            group=group,
        ),
    ]


def heater_stage_fields():
    group = 'Heater stage position'
    return [
        number(
            key,
            f'Heater {key}',
            unit,
            unit_label=label,
            archive=f'heater_stage_position.{key}',
            group=group,
        )
        for key, unit, label in (
            ('x', 'mm', None),
            ('y', 'mm', None),
            ('z', 'mm', None),
            ('tilt', 'degree', 'deg.'),
            ('spin', 'degree', 'deg.'),
        )
    ]


def heater_scan_fields():
    group = 'Heater stage scan'
    return [
        select(
            'heater_scan_type', 'Scan type', [POLAR_SCAN, CARTESIAN_SCAN], group=group
        ),
        select('heater_scan_axis', 'Scan axis', SCAN_AXES, group=group),
        select('heater_size', 'Heater size', SCAN_SIZES, group=group),
    ]


def cartesian_scan_fields(visible_if):
    group = 'Cartesian scan'
    return [
        select(
            'cartesian_area',
            'Area',
            SCAN_AREAS,
            archive='cartesian_scan.area',
            visible_if=visible_if,
            group=group,
        ),
        *[
            number(
                f'cartesian_{key}',
                label,
                unit,
                archive=f'cartesian_scan.{key}',
                visible_if=visible_if,
                group=group,
            )
            for key, label, unit in (
                ('width_x', 'Width X', 'mm'),
                ('height_z', 'Height Z', 'mm'),
                ('spot_width', 'Spot width', 'mm'),
                ('spot_height', 'Spot height', 'mm'),
                ('x_offset', 'Offset X', 'mm'),
                ('z_offset', 'Offset Z', 'mm'),
                ('scan_speed_x', 'Scan speed X', 'mm/s'),
                ('scan_speed_z', 'Scan speed Z', 'mm/s'),
            )
        ],
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
    polar = {'key': 'heater_scan_type', 'equals': POLAR_SCAN}
    cartesian = {'key': 'heater_scan_type', 'equals': CARTESIAN_SCAN}
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
        *heater_scan_fields(),
        *polar_scan_fields(polar),
        *cartesian_scan_fields(cartesian),
        *target_stage_fields(),
        temperature('substrate_temperature', 'Substrate temperature'),
        pressure('Deposition pressure'),
        *gas_fields(),
        *laser_fields(),
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
            ramp_fields('Heating pressure', heater_output()),
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
            ramp_fields('Cool-down pressure'),
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


def client_settings() -> dict:
    """Texts and settings of the page (see `static/app.js`)."""
    return {
        'title': 'PLD logbook',
        'intro': (
            'Log an SA-PLD or LA-PLD run step by step, starting from its samples. '
            'Only the fields that apply are shown, and a logbook is saved once it '
            'is complete.'
        ),
        'draft_key': 'pld-logbook-draft-v2',
        'draft_dir': DRAFT_DIR,
        'file_dir': 'pld_files',
        'upload_name': 'PLD logbooks',
        'film_steps': list(FILM_STEPS),
        'all_samples': list(ALL_SAMPLES),
        'system_notes': {
            'SA-PLD': 'In the SA-PLD a deposition covers all samples loaded in the '
            'chamber.',
        },
        'requirement_note': (
            'Not needed for these process steps: it is only logged when a step '
            'needs it (e.g. a pre-ablation or deposition step). What you enter here '
            'is not saved.'
        ),
        # No `target_entry`: new PLD targets are added by super-users in NOMAD.
    }


def form_spec() -> dict:
    """The complete form definition, as sent to the browser."""
    return {
        'client': client_settings(),
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
                'intro': (
                    'Select the targets that are in the system and enter their '
                    'target number for this run. Is a target missing? New targets '
                    'are added to the database by a super-user.'
                ),
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
                'intro': (
                    'Add the steps in the order they were done. Steps can be added '
                    'more than once, e.g. for multilayers. A run without deposition, '
                    'e.g. annealing or only characterisation, needs no laser details '
                    'or targets.'
                ),
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
