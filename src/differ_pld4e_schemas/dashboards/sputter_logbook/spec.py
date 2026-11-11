"""
Declarative definition of the sputter (SPS) logbook form. Field keys are
described in `dashboards.common.fields`, section and variant keys in
`dashboards.pld_logbook.spec`.

Step variant keys:
    target       'required' | 'none': whether the step sputters a target (and
                 so needs the targets section)
"""

from __future__ import annotations

# Importing the schema package fixes the package name that qualified section
# names (the m_def written into archive files) are built from.
import differ_pld4e_schemas.schema_packages.schema_package  # noqa: F401
from differ_pld4e_schemas.database import database_upload_id
from differ_pld4e_schemas.sample import Sample, SubstrateType
from differ_pld4e_schemas.sps_deposition import (
    CARRIERS,
    DC,
    DC_RF,
    FIXED_STAGE,
    INCH,
    PLASMA_TYPES,
    RF,
    SHUTTER,
    SPS,
    TARGET_POSITIONS,
    SPSLogbook,
)
from differ_pld4e_schemas.target import SputterTarget
from differ_pld4e_schemas.time_zone import lab_time_zone_name

from ..common.fields import field, number, sample_mask, step_comments
from ..common.samples import sample_section
from ..common.steps import (
    gas_fields,
    heater_output,
    pressure,
    ramp_fields,
    time_fields,
)
from .rules import FILM_STEPS, MASK_SYSTEMS

DRAFT_DIR = 'sps_drafts'
SYSTEMS = (SPS,)
LOGBOOK_SECTIONS = {SPS: SPSLogbook}
TARGET_STEPS = {'from_steps': 'target'}
# The power ramps are noted per 5 minutes, entered here as W/minute.
PER_5_MINUTES = 1 / 5


def _sections(name):
    return {SPS: f'SPS{name}'}


def _target_positions_help() -> str:
    sizes = ', '.join(
        f'{number}: {diameter / INCH:g}"'
        for number, diameter in TARGET_POSITIONS.items()
    )
    return f'Target diameter per position: {sizes}.'


def plasma_fields():
    """U is read for DC, the load capacitance CL for RF."""
    group = 'Plasma'
    dc = {'key': 'plasma_type', 'in': [DC, DC_RF]}
    rf = {'key': 'plasma_type', 'in': [RF, DC_RF]}
    return [
        field(
            'plasma_type',
            'Plasma',
            'select',
            options=list(PLASMA_TYPES),
            archive='plasma.plasma_type',
            group=group,
        ),
        number(
            'voltage', 'U', 'V', archive='plasma.voltage', visible_if=dc, group=group
        ),
        number(
            'load_capacitance',
            'CL',
            'nF',
            archive='plasma.load_capacitance',
            visible_if=rf,
            group=group,
        ),
        number(
            'current', 'I', 'mA', required=False, archive='plasma.current', group=group
        ),
        number(
            'dc_bias',
            'DC bias',
            'V',
            required=False,
            archive='plasma.dc_bias',
            group=group,
        ),
        number('power', 'Power', 'W', archive='plasma.power', group=group),
    ]


def power_ramp(key, label):
    return number(key, label, 'W/minute', unit_label='W/5 min', scale=PER_5_MINUTES)


def heater_fields():
    group = 'Heater'
    return [
        *[
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
                ('spin', 'degree', '°'),
            )
        ],
        number('heater_rotation', 'Heater rotation', 'rpm', group=group),
    ]


def variant(label, sections, fields, target='none', **kwargs):
    return {
        'label': label,
        'sections': sections,
        'fields': [*time_fields(), *fields],
        'target': target,
        **kwargs,
    }


def step_variants():
    target = field('target', 'Target', 'target_choice')
    pre_sputtering = [
        target,
        *gas_fields(),
        pressure('Deposition pressure'),
        *plasma_fields(),
        power_ramp('ramp_up_rate', 'Ramp up'),
        number('pre_sputter_time', 'Pre-sputter time', 'minute', unit_label='min'),
        step_comments(),
    ]
    sputtering = [
        sample_mask(),
        *heater_fields(),
        target,
        *gas_fields(),
        pressure('Deposition pressure'),
        *plasma_fields(),
        field('shutter', 'Shutter', 'select', options=list(SHUTTER), default='open'),
        number('sputter_time', 'Sputter time', 'minute', unit_label='min'),
        power_ramp('ramp_down_rate', 'Ramp down'),
        number(
            'film_thickness',
            'Film thickness',
            'nm',
            help='The film grown in this step; together with the target it makes '
            'up the sample name.',
        ),
        step_comments(),
    ]
    return {
        'pre_sputtering': variant(
            'Pre-sputtering step',
            _sections('PreSputteringStep'),
            pre_sputtering,
            target='required',
        ),
        'heating': variant(
            'Heating step',
            _sections('HeatingStep'),
            ramp_fields('Heating pressure', heater_output()),
        ),
        'sputtering': variant(
            'Sputtering step',
            _sections('SputteringStep'),
            sputtering,
            target='required',
            prefill_from='pre_sputtering',
        ),
        'cool_down': variant(
            'Cool-down step',
            _sections('CoolDownStep'),
            ramp_fields('Cool-down pressure'),
        ),
    }


def client_settings() -> dict:
    """Texts and settings of the page (see `static/app.js`)."""
    return {
        'title': 'Sputter logbook',
        'intro': (
            'Log an SPS run step by step, starting from its samples. Only the '
            'fields that apply are shown, and a logbook is saved once it is '
            'complete.'
        ),
        'draft_key': 'sps-logbook-draft-v1',
        'draft_dir': DRAFT_DIR,
        'file_dir': 'sps_files',
        'upload_name': 'SPS logbooks',
        'film_steps': list(FILM_STEPS),
        'mask_systems': list(MASK_SYSTEMS),
        'system_notes': {
            SPS: 'Sputtering currently does not support a heating step.',
        },
        'requirement_note': (
            'Not needed for these process steps: targets are only logged when a '
            'step sputters (pre-sputtering or sputtering). What you enter here is '
            'not saved.'
        ),
        'target_entry': {
            'intro': (
                'Creates a Sputter Target entry. Do not put the target number in '
                f'the name: it is entered per run. {_target_positions_help()}'
            ),
            'fields': [
                {'key': 'material', 'label': 'Material', 'required': True},
                {
                    'key': 'chemical_formula',
                    'label': 'Chemical formula',
                    'required': True,
                    'placeholder': 'e.g. Ta or TiO2, not a lab name',
                },
                {'key': 'name', 'label': 'Name (optional, defaults to material)'},
                {
                    'key': 'diameter',
                    'label': 'Diameter (inch)',
                    'required': True,
                    'placeholder': 'e.g. 2',
                    'scale': INCH,
                },
                {'key': 'manufacturer', 'label': 'Manufacturer'},
                {'key': 'purchase_date', 'label': 'Purchase date', 'type': 'date'},
            ],
        },
    }


def form_spec() -> dict:
    """The complete form definition, as sent to the browser."""
    fixed_stage = {'key': 'substrate_carrier', 'equals': FIXED_STAGE}
    return {
        'client': client_settings(),
        'systems': list(SYSTEMS),
        'logbook_sections': {
            system: section.m_def.qualified_name()
            for system, section in LOGBOOK_SECTIONS.items()
        },
        # Targets and substrates are chosen from this upload only.
        'database_upload_id': database_upload_id(),
        # The lab's clock, on which run and step times are entered.
        'lab_time_zone': lab_time_zone_name(),
        'reference_sections': {
            'target': SputterTarget.m_def.qualified_name(),
            'sample': Sample.m_def.qualified_name(),
            'substrate': SubstrateType.m_def.qualified_name(),
        },
        'sections': [
            {
                'key': 'run',
                'title': 'Run',
                'kind': 'object',
                'intro': (
                    'Who does the run and when. The system, date and time make up '
                    'the sample IDs.'
                ),
                'fields': [
                    field('operator_name', 'Name'),
                    field('operator_email', 'Email'),
                    field(
                        'system',
                        'PVD system',
                        'select',
                        options=list(SYSTEMS),
                        default=SPS,
                        archive=None,
                    ),
                    field('date', 'Date', 'date', archive=None),
                    field('time', 'Start time', 'time', archive=None),
                    field(
                        'name',
                        'Run name',
                        placeholder='optional, e.g. Ta-Ti multilayer',
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
                        options=list(CARRIERS),
                    ),
                    field(
                        'mask_used',
                        'Mask used',
                        'bool',
                        visible_if=fixed_stage,
                    ),
                    field(
                        'mask_type',
                        'Mask type',
                        visible_if={
                            'all': [fixed_stage, {'key': 'mask_used', 'equals': True}]
                        },
                    ),
                    number('base_pressure', 'Main chamber pressure', 'mbar'),
                ],
            },
            {
                'key': 'targets',
                'title': 'Targets',
                'kind': 'list',
                'item_label': 'Target',
                'min_items': 1,
                'requirement': TARGET_STEPS,
                'unique': ['target', 'target_number'],
                'intro': (
                    'Select the targets that are in the system and enter their '
                    f'target number for this run. {_target_positions_help()}'
                ),
                'fields': [
                    field(
                        'target',
                        'Target',
                        'reference',
                        reference='target',
                        # The material names the films of the samples.
                        ref_copy={'material': 'material'},
                        database=True,
                        archive=None,
                    ),
                    field(
                        'target_number',
                        'Target number',
                        'select',
                        options=[str(number) for number in TARGET_POSITIONS],
                    ),
                ],
            },
            {
                'key': 'steps',
                'title': 'Process steps',
                'kind': 'variant_list',
                'item_label': 'Step',
                'intro': (
                    'Add the steps in the order they were done. Steps can be added '
                    'more than once, e.g. a pre-sputtering and sputtering step per '
                    'layer of a multilayer.'
                ),
                'variants': step_variants(),
            },
            {
                'key': 'comments',
                'title': 'General comments',
                'kind': 'object',
                'fields': [
                    field(
                        'comments',
                        'General comments',
                        'textarea',
                        archive='description',
                    )
                ],
            },
        ],
    }
