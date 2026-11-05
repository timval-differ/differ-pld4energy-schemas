"""
Logbook of a run in the SPS sputter system. Like the PLD logbooks, a run starts
from its samples (`SampleRun`), takes its targets from the target database
(`SputterTarget`) and lists its process steps: pre-sputtering, heating,
sputtering and cool-down, repeated as needed for multilayers.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import TYPE_CHECKING

from nomad.datamodel.data import ArchiveSection, EntryData
from nomad.datamodel.metainfo.annotations import ELNAnnotation, ELNComponentEnum
from nomad.datamodel.metainfo.basesections import SystemComponent
from nomad.metainfo import MEnum, Quantity, Reference, Section, SubSection
from nomad_material_processing.vapor_deposition.pvd.general import (
    PVDEvaporationSource,
    PVDSource,
    SourcePower,
)
from nomad_material_processing.vapor_deposition.pvd.sputtering import (
    SputterDeposition,
)

from differ_pld4e_schemas import m_package
from differ_pld4e_schemas.base_sections import RunDetails
from differ_pld4e_schemas.process_steps import (
    CoolDownStep,
    GasProcessStep,
    HeatingStep,
)
from differ_pld4e_schemas.references import reference_key
from differ_pld4e_schemas.sample import Sample, SampleInRun, SampleRun, resolved
from differ_pld4e_schemas.stages import HeaterStagePosition
from differ_pld4e_schemas.target import SputterTarget

if TYPE_CHECKING:
    from nomad.datamodel.datamodel import EntryArchive
    from structlog.stdlib import BoundLogger

__all__ = [
    'SPSLogbook',
    'SPSPreSputteringStep',
    'SPSSputteringStep',
    'm_package',
]

SPS = 'SPS'
INCH = 0.0254
# Target positions of the SPS and the diameter (m) of the targets they take.
TARGET_POSITIONS = {1: 2 * INCH, 2: 2 * INCH, 3: 4 * INCH}
# A target whose diameter differs more than this (m) does not fit its position.
DIAMETER_TOLERANCE = 1e-3
FIXED_STAGE = 'Fixed stage'
CARRIERS = ('4" carrier SPS', '1 cm² sub plate', FIXED_STAGE)
DC = 'DC'
RF = 'RF'
DC_RF = 'DC+RF'
PLASMA_TYPES = (DC, RF, DC_RF)
SHUTTER = ('open', 'closed')


def _power_ramp(description: str):
    return Quantity(
        type=float,
        unit='W / s',
        description=f'{description} In the lab it is noted per 5 min: '
        '10 W/5 min is 2 W/min.',
        a_eln=ELNAnnotation(
            component=ELNComponentEnum.NumberEditQuantity,
            defaultDisplayUnit='W / minute',
        ),
    )


def _duration(description: str):
    return Quantity(
        type=float,
        unit='s',
        description=description,
        a_eln=ELNAnnotation(
            component=ELNComponentEnum.NumberEditQuantity, defaultDisplayUnit='minute'
        ),
    )


def _diameter_text(diameter) -> str:
    return f'{diameter.to("inch").magnitude:g}"'


class SelectedSputterTarget(ArchiveSection):
    """A target from the sputter target database that is loaded in the system."""

    m_def = Section(label_quantity='material')
    target_number = Quantity(
        type=int,
        description='Target position for this run: 1 and 2 take 2" targets, 3 a 4" '
        'target.',
        a_eln=ELNAnnotation(component=ELNComponentEnum.NumberEditQuantity),
    )
    target = Quantity(
        type=Reference(SputterTarget.m_def),
        a_eln=ELNAnnotation(component=ELNComponentEnum.ReferenceEditQuantity),
    )
    material = Quantity(
        type=str, description='Read-only: copied from the target entry on save.'
    )
    diameter = Quantity(
        type=float,
        unit='m',
        description='Read-only: copied from the target entry on save.',
    )


class SputterPlasma(ArchiveSection):
    """
    The plasma of a sputter step. The voltage is read for DC, the load
    capacitance (CL) for RF.
    """

    m_def = Section(label_quantity='plasma_type')
    plasma_type = Quantity(
        type=MEnum(*PLASMA_TYPES),
        description='Direct current (DC), radio frequency (RF) or both.',
        a_eln=ELNAnnotation(component=ELNComponentEnum.RadioEnumEditQuantity),
    )
    voltage = Quantity(
        type=float,
        unit='V',
        description='Voltage U (DC).',
        a_eln=ELNAnnotation(component=ELNComponentEnum.NumberEditQuantity),
    )
    load_capacitance = Quantity(
        type=float,
        unit='F',
        description='Load capacitance CL of the matching network (RF).',
        a_eln=ELNAnnotation(
            component=ELNComponentEnum.NumberEditQuantity, defaultDisplayUnit='nF'
        ),
    )
    current = Quantity(
        type=float,
        unit='A',
        description='Current I.',
        a_eln=ELNAnnotation(
            component=ELNComponentEnum.NumberEditQuantity, defaultDisplayUnit='mA'
        ),
    )
    dc_bias = Quantity(
        type=float,
        unit='V',
        description='DC bias.',
        a_eln=ELNAnnotation(
            component=ELNComponentEnum.NumberEditQuantity, label='DC bias'
        ),
    )
    power = Quantity(
        type=float,
        unit='W',
        a_eln=ELNAnnotation(component=ELNComponentEnum.NumberEditQuantity),
    )


class SputterTargetedStep(GasProcessStep):
    """
    A step that sputters one of the targets loaded in the system. Its native
    `sources` (the target and the plasma power) are filled on normalization.
    """

    m_def = Section()
    target = Quantity(
        type=Reference(SputterTarget.m_def),
        description='One of the targets selected in the target details.',
        a_eln=ELNAnnotation(component=ELNComponentEnum.ReferenceEditQuantity),
    )
    target_number = Quantity(
        type=int,
        description='Read-only: taken from the target details on save.',
    )
    plasma = SubSection(section_def=SputterPlasma)

    def normalize(self, archive: EntryArchive, logger: BoundLogger) -> None:
        super().normalize(archive, logger)
        self.fill_sources()

    def fill_sources(self) -> None:
        """
        The native sources. Called again by the logbook, which may set the
        target after the step is normalized.
        """
        self.sources = [self._source()] if self.target is not None else []

    def _source(self) -> PVDSource:
        name, material = resolved(self.target, 'name', 'material')
        power = self.plasma.power if self.plasma is not None else None
        return PVDSource(
            name=self.m_def.label,
            material=[SystemComponent(name=name or material, system=self.target)],
            vapor_source=PVDEvaporationSource(
                power=SourcePower(set_value=[power.to('W').magnitude], set_time=[0])
            )
            if power is not None
            else None,
        )


class PreSputteringStep(SputterTargetedStep):
    """Cleaning the target with the shutter closed before sputtering."""

    m_def = Section(label='Pre-sputtering step')
    ramp_up_rate = _power_ramp('Rate at which the power is ramped up.')
    pre_sputter_time = _duration('Time the target is pre-sputtered.')


class SputteringStep(SputterTargetedStep):
    """Grows one film, from the step's target, on all samples of the run."""

    m_def = Section(label='Sputtering step')
    heater_stage_position = SubSection(section_def=HeaterStagePosition)
    heater_rotation = Quantity(
        type=float,
        unit='rpm',
        description='Rotation of the heater.',
        a_eln=ELNAnnotation(component=ELNComponentEnum.NumberEditQuantity),
    )
    shutter = Quantity(
        type=MEnum(*SHUTTER),
        a_eln=ELNAnnotation(component=ELNComponentEnum.RadioEnumEditQuantity),
    )
    sputter_time = _duration('Time the samples are sputtered on.')
    ramp_down_rate = _power_ramp('Rate at which the power is ramped down.')
    film_thickness = Quantity(
        type=float,
        unit='m',
        description='Intended thickness of the film grown in this step.',
        a_eln=ELNAnnotation(
            component=ELNComponentEnum.NumberEditQuantity, defaultDisplayUnit='nm'
        ),
    )
    samples = Quantity(
        type=Reference(Sample.m_def),
        shape=['*'],
        description='The samples deposited on.',
        a_eln=ELNAnnotation(component=ELNComponentEnum.ReferenceEditQuantity),
    )

    def normalize(self, archive: EntryArchive, logger: BoundLogger) -> None:
        self.creates_new_thin_film = True
        super().normalize(archive, logger)


# The SPS gets its own step classes so that the GUI only offers sputter steps
# (and never a PLD step) when a step is added.


class SPSStep(GasProcessStep):
    """A process step of the SPS system."""

    m_def = Section(label='SPS step')


class SPSPreSputteringStep(PreSputteringStep, SPSStep):
    m_def = Section(label='Pre-sputtering step')


class SPSHeatingStep(HeatingStep, SPSStep):
    m_def = Section(label='Heating step')


class SPSSputteringStep(SputteringStep, SPSStep):
    m_def = Section(label='Sputtering step')


class SPSCoolDownStep(CoolDownStep, SPSStep):
    m_def = Section(label='Cool-down step')


class SPSLogbook(SampleRun, RunDetails, SputterDeposition, EntryData):
    """
    Electronic lab notebook of one run in the SPS sputter system. A run starts
    with the samples it makes or processes (`samples`). Use `description` for
    general comments.
    """

    m_def = Section(label='SPS Logbook')
    pvd_system = Quantity(
        type=str,
        default=SPS,
        description='Read-only: fixed by the logbook type.',
    )
    substrate_carrier = Quantity(
        type=MEnum(*CARRIERS),
        a_eln=ELNAnnotation(component=ELNComponentEnum.EnumEditQuantity),
    )
    mask_used = Quantity(
        type=bool,
        description='Whether a mask is used on the fixed stage.',
        a_eln=ELNAnnotation(component=ELNComponentEnum.BoolEditQuantity),
    )
    mask_type = Quantity(
        type=str,
        description='The mask used on the fixed stage.',
        a_eln=ELNAnnotation(component=ELNComponentEnum.StringEditQuantity),
    )
    base_pressure = Quantity(
        type=float,
        unit='Pa',
        description='Pressure of the main chamber before the run.',
        a_eln=ELNAnnotation(
            component=ELNComponentEnum.NumberEditQuantity, defaultDisplayUnit='mbar'
        ),
    )
    # Declared here: the native `samples` of the process would win over
    # those of `SampleRun`.
    samples = SubSection(section_def=SampleInRun, repeats=True)
    targets = SubSection(section_def=SelectedSputterTarget, repeats=True)
    steps = SubSection(section_def=SPSStep, repeats=True)

    def normalize(self, archive: EntryArchive, logger: BoundLogger) -> None:
        if self.datetime is None:
            self.datetime = datetime.now(timezone.utc)
        # Store the system: NOMAD does not show a default as a value.
        if not self.m_is_set(self.m_def.all_quantities['pvd_system']):
            self.pvd_system = SPS
        self.default_name(self.pvd_system)
        if self.mask_used and self.substrate_carrier != FIXED_STAGE:
            logger.warning('A mask is only used with the fixed stage.')
        self._normalize_targets(logger)
        self._normalize_samples(archive, logger, self.pvd_system, self.datetime)
        self._normalize_step_targets(logger)
        super().normalize(archive, logger)

    def _normalize_targets(self, logger: BoundLogger) -> None:
        seen_targets, seen_numbers = set(), set()
        for selected in self.targets or []:
            target = selected.target
            if target is not None:
                key = reference_key(target)
                if key in seen_targets:
                    logger.error(f'Target {target.name} is selected more than once.')
                seen_targets.add(key)
                selected.material = target.material
                selected.diameter = target.diameter
            number = selected.target_number
            if number is None:
                continue
            if number not in TARGET_POSITIONS:
                logger.warning(
                    f'Target number {number} is not a position in the system '
                    f'({min(TARGET_POSITIONS)} to {max(TARGET_POSITIONS)}).'
                )
            elif (
                selected.diameter is not None
                and abs(selected.diameter.to('m').magnitude - TARGET_POSITIONS[number])
                > DIAMETER_TOLERANCE
            ):
                logger.warning(
                    f'Target {number} takes {TARGET_POSITIONS[number] / INCH:g}" '
                    f'targets, but {selected.material or "the target"} is '
                    f'{_diameter_text(selected.diameter)}.'
                )
            if number in seen_numbers:
                logger.warning(f'Target number {number} is used twice.')
            seen_numbers.add(number)

    def _normalize_step_targets(self, logger: BoundLogger) -> None:
        selected = [t for t in self.targets or [] if t.target is not None]
        for step in self.steps or []:
            if not isinstance(step, SputterTargetedStep):
                continue
            if step.target is None and len(selected) == 1:
                step.target = selected[0].target
            if step.target is None:
                step.target_number = None
                continue
            key = reference_key(step.target)
            match = next((t for t in selected if reference_key(t.target) == key), None)
            if match is None:
                logger.warning(
                    f'Step "{step.name or step.m_def.label}" uses a target that is '
                    'not selected in the target details.'
                )
            step.target_number = match.target_number if match else None
            step.fill_sources()
