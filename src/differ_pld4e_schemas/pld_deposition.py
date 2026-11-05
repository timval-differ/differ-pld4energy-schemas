"""
Logbooks of the SA-PLD and LA-PLD. A logbook is a native NOMAD
`PulsedLaserDeposition` process, so NOMAD's search knows its method; its steps
are native PLD steps, whose `sources` (target and laser) and `sample_parameters`
are filled from what is entered.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import TYPE_CHECKING

from nomad.datamodel.data import ArchiveSection, EntryData
from nomad.datamodel.metainfo.annotations import ELNAnnotation, ELNComponentEnum
from nomad.datamodel.metainfo.basesections import Process
from nomad.metainfo import Datetime, MEnum, Quantity, Reference, Section, SubSection
from nomad_material_processing.vapor_deposition.pvd.pld import (
    PLDLaser,
    PLDSource,
    PLDStep,
    PLDTargetComponent,
    PulsedLaserDeposition,
)

from differ_pld4e_schemas import m_package
from differ_pld4e_schemas.base_sections import RunDetails
from differ_pld4e_schemas.database import check_database_reference
from differ_pld4e_schemas.in_situ import InSituTechniques
from differ_pld4e_schemas.laser import LaserCalibration, LaserParameters
from differ_pld4e_schemas.process_steps import (
    CoolDownStep,
    GasProcessStep,
    HeatingStep,
    SetpointStep,
    substrate_temperature_parameters,
)
from differ_pld4e_schemas.process_steps import (
    heater_output_quantity as _heater_output,
)
from differ_pld4e_schemas.process_steps import (
    heating_mode_quantity as _heating_mode,
)
from differ_pld4e_schemas.process_steps import (
    temperature_quantity as _temperature,
)
from differ_pld4e_schemas.references import copy_section as _copy
from differ_pld4e_schemas.references import reference_key as _reference_key
from differ_pld4e_schemas.sample import Sample, SampleInRun, SampleRun, resolved
from differ_pld4e_schemas.stages import (
    HEATER_SIZES,
    SCAN_AXES,
    CartesianHeaterScan,
    HeaterStagePosition,
    PolarHeaterScan,
    TargetStage,
    choice,
)
from differ_pld4e_schemas.target import PLDTarget

if TYPE_CHECKING:
    from nomad.datamodel.datamodel import EntryArchive
    from structlog.stdlib import BoundLogger

__all__ = [
    'CoolDownStep',
    'HeatingStep',
    'LAPLDDepositionStep',
    'LAPLDLogbook',
    'PLDLogbook',
    'SAPLDDepositionStep',
    'SAPLDLogbook',
    'm_package',
]

POLAR_SCAN = 'Polar scan'
CARTESIAN_SCAN = 'Cartesian scan'
# The intended thickness of a film is given in nm or as a number of pulses.
THICKNESS_IN_NM = 'nm'
THICKNESS_IN_PULSES = 'pulses'
THICKNESS_UNITS = (THICKNESS_IN_NM, THICKNESS_IN_PULSES)
# Usual setting (%) of the laser output limitation knob of the SA-PLD.
LASER_OUTPUT_LIMITATION = 50.0
# Positions in the target carousel.
TARGET_NUMBERS = range(1, 6)
CARRIERS = {
    'SA-PLD': ('Omicron carrier', '1" carrier'),
    'LA-PLD': (
        'Omicron carrier',
        '1" carrier',
        '4" wafer carrier',
        'Sample select carrier',
    ),
}


class SelectedTarget(ArchiveSection):
    """A target from the target database that is loaded in the system."""

    m_def = Section(label_quantity='material')
    target_number = Quantity(
        type=int,
        description='Position of the target in the system for this run (1 to 5).',
        a_eln=ELNAnnotation(component=ELNComponentEnum.NumberEditQuantity),
    )
    target = Quantity(
        type=Reference(PLDTarget.m_def),
        a_eln=ELNAnnotation(component=ELNComponentEnum.ReferenceEditQuantity),
    )
    material = Quantity(
        type=str, description='Read-only: copied from the target entry on save.'
    )
    manufacturer = Quantity(
        type=str, description='Read-only: copied from the target entry on save.'
    )
    purchase_date = Quantity(
        type=Datetime, description='Read-only: copied from the target entry on save.'
    )


class RecipeLoader(ArchiveSection):
    """
    Reproduce the process steps of an earlier run on the samples of this run.
    Select the recipe (and optionally one sample), tick `apply_recipe` and save:
    the steps of the recipe are appended to the steps of this logbook and its
    deposition steps are linked to the samples. Laser details, samples and
    in-situ data of the recipe are not copied.
    """

    m_def = Section(label='Load recipe')
    recipe = Quantity(
        type=Reference(Process.m_def),
        description="""
        An earlier logbook of the same PLD system (an SA-PLD recipe can only be
        applied to an SA-PLD logbook, an LA-PLD recipe to an LA-PLD logbook).
        """,
        a_eln=ELNAnnotation(component=ELNComponentEnum.ReferenceEditQuantity),
    )
    sample = Quantity(
        type=Reference(Sample.m_def),
        description="""
        Sample the copied deposition steps are linked to. If empty, all samples
        of this logbook are used.
        """,
        a_eln=ELNAnnotation(component=ELNComponentEnum.ReferenceEditQuantity),
    )
    apply_recipe = Quantity(
        type=bool,
        default=False,
        description="""
        Tick and save to copy the recipe steps. It is unticked again after the
        copy, so a later save does not copy the steps a second time.
        """,
        a_eln=ELNAnnotation(component=ELNComponentEnum.BoolEditQuantity),
    )
    applied_recipe = Quantity(
        type=str,
        description='Read-only: name of the last recipe that was applied.',
    )


class PLDProcessStep(GasProcessStep, PLDStep):
    """Common part of all PLD process steps. Use `comment` for comments."""

    m_def = Section()


class TargetedStep(PLDProcessStep):
    """
    A step that ablates one of the targets loaded in the system. Its native
    `sources` (the target and the laser) and `sample_parameters` (the substrate
    temperature) are filled on normalization.
    """

    m_def = Section()
    target = Quantity(
        type=Reference(PLDTarget.m_def),
        description='One of the targets selected in the target details.',
        a_eln=ELNAnnotation(component=ELNComponentEnum.ReferenceEditQuantity),
    )
    target_number = Quantity(
        type=int,
        description='Read-only: taken from the target details on save.',
    )
    substrate_temperature = _temperature()
    target_stage = SubSection(section_def=TargetStage)
    laser = SubSection(section_def=LaserParameters)

    def normalize(self, archive: EntryArchive, logger: BoundLogger) -> None:
        super().normalize(archive, logger)
        self.fill_sources()

    def fill_sources(self) -> None:
        """
        The native sources and sample parameters. Called again by the logbook,
        which may set the target after the step is normalized.
        """
        self.sources = [self._source()] if self.target is not None else []
        self.sample_parameters = substrate_temperature_parameters(
            self.substrate_temperature
        )

    def _source(self) -> PLDSource:
        laser = self.laser
        name, material, lab_id = resolved(self.target, 'name', 'material', 'lab_id')
        return PLDSource(
            name=self.m_def.label,
            material=[
                PLDTargetComponent(
                    name=name or material, system=self.target, lab_id=lab_id
                )
            ],
            vapor_source=PLDLaser(
                pulses=laser.number_of_laser_pulses,
                repetition_rate=laser.laser_frequency,
                spot_size=laser.spot_size,
            )
            if laser is not None
            else None,
        )


class PreAblationStep(TargetedStep):
    m_def = Section(label='Pre-ablation step')


class AnnealingStep(SetpointStep, PLDProcessStep):
    """Keeping the samples at a temperature, e.g. in a run without deposition."""

    m_def = Section(label='Annealing step')
    heater_output = _heater_output()
    dwell_time = Quantity(
        type=float,
        unit='s',
        description='Time at the temperature setpoint.',
        a_eln=ELNAnnotation(
            component=ELNComponentEnum.NumberEditQuantity, defaultDisplayUnit='minute'
        ),
    )


class PLDDepositionStep(TargetedStep):
    """Grows one film, from the step's target, on each of its samples."""

    m_def = Section(label='Pulsed laser deposition step')
    film_thickness_unit = Quantity(
        type=MEnum(*THICKNESS_UNITS),
        default=THICKNESS_IN_NM,
        description='Whether the intended thickness is given in nm or as a number '
        'of laser pulses.',
        a_eln=ELNAnnotation(component=ELNComponentEnum.RadioEnumEditQuantity),
    )
    film_thickness = Quantity(
        type=float,
        unit='m',
        description='Intended thickness of the film grown in this step.',
        a_eln=ELNAnnotation(
            component=ELNComponentEnum.NumberEditQuantity, defaultDisplayUnit='nm'
        ),
    )
    film_thickness_pulses = Quantity(
        type=int,
        description='Intended thickness of the film as a number of laser pulses.',
        a_eln=ELNAnnotation(
            component=ELNComponentEnum.NumberEditQuantity,
            label='Film thickness (pulses)',
        ),
    )
    samples = Quantity(
        type=Reference(Sample.m_def),
        shape=['*'],
        description='The samples deposited on.',
        a_eln=ELNAnnotation(component=ELNComponentEnum.ReferenceEditQuantity),
    )
    heater_stage_position = SubSection(section_def=HeaterStagePosition)
    heater_scan_type = Quantity(
        type=MEnum(POLAR_SCAN, CARTESIAN_SCAN),
        default=POLAR_SCAN,
        description='Fill in the scan sub-section that matches the scan type.',
        a_eln=ELNAnnotation(component=ELNComponentEnum.RadioEnumEditQuantity),
    )
    heater_scan_axis = choice(SCAN_AXES)
    heater_size = choice(HEATER_SIZES)
    polar_scan = SubSection(section_def=PolarHeaterScan)
    cartesian_scan = SubSection(section_def=CartesianHeaterScan)

    def normalize(self, archive: EntryArchive, logger: BoundLogger) -> None:
        self.creates_new_thin_film = True
        super().normalize(archive, logger)
        scan_type = self.heater_scan_type or POLAR_SCAN
        if scan_type == POLAR_SCAN:
            if self.polar_scan is None:
                self.polar_scan = PolarHeaterScan()
            if self.cartesian_scan is not None:
                logger.warning(
                    'Cartesian scan parameters are ignored for a polar scan.'
                )
        else:
            if self.cartesian_scan is None:
                self.cartesian_scan = CartesianHeaterScan()
            if self.polar_scan is not None:
                logger.warning(
                    'Polar scan parameters are ignored for a cartesian scan.'
                )


def _switch(description):
    return Quantity(
        type=bool,
        default=False,
        description=description,
        a_eln=ELNAnnotation(component=ELNComponentEnum.BoolEditQuantity),
    )


def _number(unit, label, description, **kwargs):
    return Quantity(
        type=float,
        unit=unit,
        description=description,
        a_eln=ELNAnnotation(component=ELNComponentEnum.NumberEditQuantity, label=label),
        **kwargs,
    )


def _ramp_on():
    return _switch('Whether the ramp was on (Ramp On/Off).')


# The heater settings follow the "Temperature control" panel of the system
# software.


class HeaterControl(ArchiveSection):
    """Switches of the temperature control, shared by SA-PLD and LA-PLD."""

    m_def = Section()
    fix_output = _switch('Whether the heater output was fixed (Fix output).')
    drift_compensation = _switch('Whether drift compensation was on.')


class SAPLDHeaterControl(HeaterControl):
    """Laser heating of the SA-PLD."""

    m_def = Section()
    heating_mode = _heating_mode()
    power_setpoint = _number(
        None,
        'Power setpoint (%)',
        'Setpoint in laser heating (power) mode.',
    )
    laser_output_limitation = _number(
        None,
        'Laser output limitation (%)',
        'Limit set with the knob on the laser output limitation unit.',
        default=LASER_OUTPUT_LIMITATION,
    )


class LAPLDHeaterControl(HeaterControl):
    """Main heater power supply of the LA-PLD."""

    m_def = Section()
    supply_voltage = _number('V', None, 'Voltage set on the power supply.')
    supply_current = _number('A', None, 'Current set on the power supply.')
    actual_voltage = _number('V', None, 'Voltage read out on the power supply.')
    actual_current = _number('A', None, 'Current read out on the power supply.')


# SA-PLD and LA-PLD each get their own step classes so that the GUI only offers
# the steps of that system (and never a sputter step) when a step is added.


class SAPLDStep(PLDProcessStep):
    """A process step of the SA-PLD system."""

    m_def = Section(label='SA-PLD step')


class SAPLDPreAblationStep(PreAblationStep, SAPLDStep):
    m_def = Section(label='Pre-ablation step')


class SAPLDHeatingStep(HeatingStep, SAPLDHeaterControl, SAPLDStep):
    m_def = Section(label='Heating step')
    ramp_on = _ramp_on()
    power_ramp_rate = _number(
        None, 'Ramp rate (%/min)', 'Ramp rate in laser heating (power) mode.'
    )


class SAPLDAnnealingStep(AnnealingStep, SAPLDHeaterControl, SAPLDStep):
    m_def = Section(label='Annealing step')


class SAPLDDepositionStep(PLDDepositionStep, SAPLDHeaterControl, SAPLDStep):
    """Deposits on all samples loaded in the chamber."""

    m_def = Section(label='Pulsed laser deposition step')


class SAPLDCoolDownStep(CoolDownStep, SAPLDHeaterControl, SAPLDStep):
    m_def = Section(label='Cool-down step')
    ramp_on = _ramp_on()
    power_ramp_rate = _number(
        None, 'Ramp rate (%/min)', 'Ramp rate in laser heating (power) mode.'
    )


class LAPLDStep(PLDProcessStep):
    """A process step of the LA-PLD system."""

    m_def = Section(label='LA-PLD step')


class LAPLDPreAblationStep(PreAblationStep, LAPLDStep):
    m_def = Section(label='Pre-ablation step')


class LAPLDHeatingStep(HeatingStep, LAPLDHeaterControl, LAPLDStep):
    m_def = Section(label='Heating step')
    ramp_on = _ramp_on()


class LAPLDAnnealingStep(AnnealingStep, LAPLDHeaterControl, LAPLDStep):
    m_def = Section(label='Annealing step')


class LAPLDDepositionStep(PLDDepositionStep, LAPLDHeaterControl, LAPLDStep):
    m_def = Section(label='Pulsed laser deposition step')


class LAPLDCoolDownStep(CoolDownStep, LAPLDHeaterControl, LAPLDStep):
    m_def = Section(label='Cool-down step')
    ramp_on = _ramp_on()


class PLDLogbook(SampleRun, RunDetails, PulsedLaserDeposition, EntryData):
    """
    Electronic lab notebook of one PLD run. Use SA-PLD or LA-PLD logbook. A run
    starts with the samples it makes or processes (`samples`).
    """

    m_def = Section()
    pvd_system = Quantity(
        type=str,
        description='Read-only: fixed by the logbook type (SA-PLD or LA-PLD).',
    )
    base_pressure = Quantity(
        type=float,
        unit='Pa',
        description='System base pressure.',
        a_eln=ELNAnnotation(
            component=ELNComponentEnum.NumberEditQuantity, defaultDisplayUnit='mbar'
        ),
    )
    # Declared here: the native `samples` of the process would win over
    # those of `SampleRun`.
    samples = SubSection(section_def=SampleInRun, repeats=True)
    laser_details = SubSection(section_def=LaserCalibration)
    targets = SubSection(section_def=SelectedTarget, repeats=True)
    load_recipe = SubSection(section_def=RecipeLoader)
    in_situ_measurements = SubSection(
        section_def=InSituTechniques,
        repeats=True,
        description='In-situ measurements of the run, each on one sample during '
        'one or more process steps.',
    )
    system_logfiles = Quantity(
        type=str,
        shape=['*'],
        description='Logfiles of the run exported from the TSST software (.txt).',
        a_browser={'adaptor': 'RawFileAdaptor'},
        a_eln=ELNAnnotation(component=ELNComponentEnum.FileEditQuantity),
    )

    def normalize(self, archive: EntryArchive, logger: BoundLogger) -> None:
        if self.datetime is None:
            self.datetime = datetime.now(timezone.utc)
        # Store the system: NOMAD does not show a default as a value.
        pvd_system = self.m_def.all_quantities['pvd_system']
        if not self.m_is_set(pvd_system) and pvd_system.default is not None:
            self.pvd_system = pvd_system.default
        if self.laser_details is None:
            self.laser_details = LaserCalibration()
        self.default_name(self.pvd_system)
        self._normalize_targets(archive, logger)
        self._normalize_samples(archive, logger, self.pvd_system, self.datetime)
        self._apply_recipe(logger)
        self._normalize_step_targets(logger)
        super().normalize(archive, logger)

    def _normalize_targets(self, archive: EntryArchive, logger: BoundLogger) -> None:
        seen_targets, seen_numbers = set(), set()
        for selected in self.targets or []:
            target = selected.target
            if target is not None:
                check_database_reference(target, archive, logger, 'target')
                key = _reference_key(target)
                if key in seen_targets:
                    logger.error(f'Target {target.name} is selected more than once.')
                seen_targets.add(key)
                selected.material = target.material
                selected.manufacturer = target.manufacturer
                selected.purchase_date = target.purchase_date
            if selected.target_number is not None:
                if selected.target_number not in TARGET_NUMBERS:
                    logger.warning(
                        f'Target number {selected.target_number} is not a position '
                        f'in the system ({TARGET_NUMBERS[0]} to {TARGET_NUMBERS[-1]}).'
                    )
                if selected.target_number in seen_numbers:
                    logger.warning(
                        f'Target number {selected.target_number} is used twice.'
                    )
                seen_numbers.add(selected.target_number)

    def _apply_recipe(self, logger: BoundLogger) -> None:
        loader = self.load_recipe
        if loader is None or not loader.apply_recipe:
            return
        loader.apply_recipe = False
        if 'steps' not in self.m_def.all_sub_sections:
            return
        recipe = loader.recipe
        if recipe is None:
            logger.error('Select a recipe before applying it.')
            return
        if not isinstance(recipe, type(self)):
            logger.error(
                f'The recipe is from {recipe.m_def.name}, not from {self.m_def.name}.'
            )
            return
        if loader.sample is not None:
            samples = [loader.sample]
        else:
            samples = [item.reference for item in self.samples or [] if item.reference]
        sub_sections = self.m_def.all_sub_sections
        if not self.targets:
            for selected in recipe.targets or []:
                self.m_add_sub_section(sub_sections['targets'], _copy(selected))
        for step in recipe.steps or []:
            copied = _copy(step)
            if isinstance(copied, PLDDepositionStep):
                copied.samples = samples or None
            self.m_add_sub_section(sub_sections['steps'], copied)
        loader.applied_recipe = recipe.name or recipe.lab_id or 'unnamed recipe'

    def _normalize_step_targets(self, logger: BoundLogger) -> None:
        selected = [t for t in self.targets or [] if t.target is not None]
        for step in getattr(self, 'steps', None) or []:
            if not isinstance(step, TargetedStep):
                continue
            if step.target is None and len(selected) == 1:
                step.target = selected[0].target
            if step.target is None:
                step.target_number = None
                continue
            key = _reference_key(step.target)
            match = next((t for t in selected if _reference_key(t.target) == key), None)
            if match is None:
                logger.warning(
                    f'Step "{step.name or step.m_def.label}" uses a target that is '
                    'not selected in the target details.'
                )
            step.target_number = match.target_number if match else None
            step.fill_sources()


class SAPLDLogbook(PLDLogbook):
    """Electronic lab notebook of an SA-PLD run."""

    m_def = Section(label='SA-PLD Logbook')
    pvd_system = Quantity(
        type=str,
        default='SA-PLD',
        description='Read-only: fixed by the logbook type.',
    )
    substrate_carrier = Quantity(
        type=MEnum(*CARRIERS['SA-PLD']),
        a_eln=ELNAnnotation(component=ELNComponentEnum.EnumEditQuantity),
    )
    steps = SubSection(section_def=SAPLDStep, repeats=True)


class LAPLDLogbook(PLDLogbook):
    """Electronic lab notebook of an LA-PLD run."""

    m_def = Section(label='LA-PLD Logbook')
    pvd_system = Quantity(
        type=str,
        default='LA-PLD',
        description='Read-only: fixed by the logbook type.',
    )
    substrate_carrier = Quantity(
        type=MEnum(*CARRIERS['LA-PLD']),
        a_eln=ELNAnnotation(component=ELNComponentEnum.EnumEditQuantity),
    )
    particle_reduction_plate = Quantity(
        type=MEnum('in use', 'not in use'),
        a_eln=ELNAnnotation(component=ELNComponentEnum.RadioEnumEditQuantity),
    )
    steps = SubSection(section_def=LAPLDStep, repeats=True)
