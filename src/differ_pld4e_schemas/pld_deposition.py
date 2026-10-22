from __future__ import annotations

import re
import uuid
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from nomad.datamodel.data import ArchiveSection, EntryData
from nomad.datamodel.metainfo.annotations import ELNAnnotation, ELNComponentEnum
from nomad.metainfo import Datetime, MEnum, Quantity, Reference, Section, SubSection
from nomad.metainfo.metainfo import MetainfoReferenceError

from differ_pld4e_schemas import m_package
from differ_pld4e_schemas.base_sections import Process, ProcessStep
from differ_pld4e_schemas.gas import BackgroundGas
from differ_pld4e_schemas.in_situ import InSituTechniques
from differ_pld4e_schemas.laser import LaserCalibration, LaserParameters
from differ_pld4e_schemas.pld_substrate import (
    NewSubstrate,
    PLDSubstrate,
    sample_user_id,
)
from differ_pld4e_schemas.stages import (
    CartesianHeaterScan,
    HeaterStagePosition,
    PolarHeaterScan,
    TargetStage,
)
from differ_pld4e_schemas.target import PLDTarget

if TYPE_CHECKING:
    from nomad.datamodel.datamodel import EntryArchive
    from structlog.stdlib import BoundLogger

__all__ = [
    'LAPLDDepositionStep',
    'LAPLDLogbook',
    'PLDLogbook',
    'SAPLDDepositionStep',
    'SAPLDLogbook',
    'm_package',
]

POLAR_SCAN = 'Polar scan'
CARTESIAN_SCAN = 'Cartesian scan'


def _temperature(**kwargs):
    return Quantity(
        type=float,
        unit='K',
        a_eln=ELNAnnotation(
            component=ELNComponentEnum.NumberEditQuantity, defaultDisplayUnit='celsius'
        ),
        **kwargs,
    )


def _ramp_rate():
    return Quantity(
        type=float,
        unit='K / minute',
        description='Ramp rate; 1 K/min equals 1 °C/min.',
        a_eln=ELNAnnotation(component=ELNComponentEnum.NumberEditQuantity),
    )


def _reference_key(section):
    """Compare references whether they are resolved sections or proxies."""
    url = getattr(section, 'm_proxy_value', None)
    if isinstance(url, str):
        match = re.search(r'archive/([^#/]+)#/?(.*)$', url)
        if match:
            return match.group(1), match.group(2) or 'data'
        return url
    return id(section)


def _absolute_reference(value):
    """
    References to entries in the same upload are stored as '../upload/...', which
    would point into the wrong upload once copied to a logbook in another upload.
    Rewrite them as '../uploads/<upload_id>/...'; other values are kept as they are.
    """
    url = getattr(value, 'm_proxy_value', None)
    if isinstance(url, str) and not url.startswith('../upload/'):
        return value
    try:
        resolved = value.m_proxy_resolve() if isinstance(url, str) else value
        metadata = resolved.m_root().metadata
    except (AttributeError, MetainfoReferenceError):
        return value
    if metadata is None or not metadata.upload_id or not metadata.entry_id:
        return value
    return (
        f'../uploads/{metadata.upload_id}/archive/{metadata.entry_id}'
        f'#{resolved.m_path()}'
    )


def _copy(section):
    """Copy a section with its sub-sections; references are kept, not copied."""
    copied = section.m_def.section_cls()
    for quantity in section.m_def.all_quantities.values():
        if section.m_is_set(quantity):
            value = section.m_get(quantity)
            if isinstance(quantity.type, Reference):
                value = _absolute_reference(value)
            copied.m_set(quantity, value)
    for sub_section in section.m_def.all_sub_sections.values():
        for child in section.m_get_sub_sections(sub_section):
            copied.m_add_sub_section(sub_section, _copy(child))
    return copied


class SelectedTarget(ArchiveSection):
    """A target from the target database that is loaded in the system."""

    m_def = Section(label_quantity='material')
    target_number = Quantity(
        type=int,
        description='Target number in the system for this run, entered by the user.',
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
    Reproduce the process steps of an earlier run on a substrate of this run.
    Select the recipe and the substrate, tick `apply_recipe` and save: the steps
    of the recipe are appended to the steps of this logbook and its deposition
    steps are linked to the chosen substrate. Laser details, substrates and
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
    substrate = Quantity(
        type=Reference(PLDSubstrate.m_def),
        description="""
        Substrate the copied deposition steps are linked to. If empty, the first
        substrate created in this logbook is used.
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


class PLDProcessStep(ProcessStep):
    """Common part of all PLD process steps. Use `description` for comments."""

    m_def = Section()
    pressure = Quantity(
        type=float,
        unit='Pa',
        description='Chamber pressure during the step.',
        a_eln=ELNAnnotation(
            component=ELNComponentEnum.NumberEditQuantity, defaultDisplayUnit='mbar'
        ),
    )
    background_gases = SubSection(section_def=BackgroundGas, repeats=True)


class TargetedStep(PLDProcessStep):
    """A step that ablates one of the targets loaded in the system."""

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


class PreAblationStep(TargetedStep):
    m_def = Section(label='Pre-ablation step')


class HeatingStep(PLDProcessStep):
    m_def = Section(label='Heating step')
    ramp_rate = _ramp_rate()
    temperature_setpoint = _temperature()


class CoolDownStep(PLDProcessStep):
    m_def = Section(label='Cool-down step')
    ramp_rate = _ramp_rate()
    temperature_setpoint = _temperature()


class PLDDepositionStep(TargetedStep):
    m_def = Section(label='Pulsed laser deposition step')
    substrate = Quantity(
        type=Reference(PLDSubstrate.m_def),
        a_eln=ELNAnnotation(component=ELNComponentEnum.ReferenceEditQuantity),
    )
    heater_stage_position = SubSection(section_def=HeaterStagePosition)


# SA-PLD and LA-PLD each get their own step classes so that the GUI only offers
# the steps of that system (and never a sputter step) when a step is added.


class SAPLDStep(PLDProcessStep):
    """A process step of the SA-PLD system."""

    m_def = Section(label='SA-PLD step')


class SAPLDPreAblationStep(PreAblationStep, SAPLDStep):
    m_def = Section(label='Pre-ablation step')


class SAPLDHeatingStep(HeatingStep, SAPLDStep):
    m_def = Section(label='Heating step')


class SAPLDDepositionStep(PLDDepositionStep, SAPLDStep):
    m_def = Section(label='Pulsed laser deposition step')
    substrate_stage_scan = Quantity(
        type=bool,
        default=False,
        a_eln=ELNAnnotation(component=ELNComponentEnum.BoolEditQuantity),
    )
    cartesian_scan = SubSection(section_def=CartesianHeaterScan)

    def normalize(self, archive: EntryArchive, logger: BoundLogger) -> None:
        super().normalize(archive, logger)
        if self.substrate_stage_scan and self.cartesian_scan is None:
            self.cartesian_scan = CartesianHeaterScan()
        elif not self.substrate_stage_scan and self.cartesian_scan is not None:
            logger.warning('Scan parameters are given but substrate stage scan is off.')


class SAPLDCoolDownStep(CoolDownStep, SAPLDStep):
    m_def = Section(label='Cool-down step')


class LAPLDStep(PLDProcessStep):
    """A process step of the LA-PLD system."""

    m_def = Section(label='LA-PLD step')


class LAPLDPreAblationStep(PreAblationStep, LAPLDStep):
    m_def = Section(label='Pre-ablation step')


class LAPLDHeatingStep(HeatingStep, LAPLDStep):
    m_def = Section(label='Heating step')


class LAPLDDepositionStep(PLDDepositionStep, LAPLDStep):
    """Fill in the scan sub-section that matches the heater scan type."""

    m_def = Section(label='Pulsed laser deposition step')
    heater_scan_type = Quantity(
        type=MEnum(POLAR_SCAN, CARTESIAN_SCAN),
        default=POLAR_SCAN,
        a_eln=ELNAnnotation(component=ELNComponentEnum.RadioEnumEditQuantity),
    )
    polar_scan = SubSection(section_def=PolarHeaterScan)
    cartesian_scan = SubSection(section_def=CartesianHeaterScan)

    def normalize(self, archive: EntryArchive, logger: BoundLogger) -> None:
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


class LAPLDCoolDownStep(CoolDownStep, LAPLDStep):
    m_def = Section(label='Cool-down step')


class PLDLogbook(Process, EntryData):
    """Electronic lab notebook of one PLD run. Use SA-PLD or LA-PLD logbook."""

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
    laser_details = SubSection(section_def=LaserCalibration)
    targets = SubSection(section_def=SelectedTarget, repeats=True)
    substrates = SubSection(section_def=NewSubstrate, repeats=True)
    load_recipe = SubSection(section_def=RecipeLoader)
    in_situ_techniques = SubSection(section_def=InSituTechniques)

    def normalize(self, archive: EntryArchive, logger: BoundLogger) -> None:
        if self.datetime is None:
            self.datetime = datetime.now(timezone.utc)
        # Store the system: NOMAD does not show a default as a value.
        pvd_system = self.m_def.all_quantities['pvd_system']
        if not self.m_is_set(pvd_system) and pvd_system.default is not None:
            self.pvd_system = pvd_system.default
        if self.laser_details is None:
            self.laser_details = LaserCalibration()
        self._normalize_targets(logger)
        self._normalize_substrates(archive, logger)
        self._apply_recipe(logger)
        self._normalize_step_targets(logger)
        super().normalize(archive, logger)

    def _normalize_targets(self, logger: BoundLogger) -> None:
        seen_targets, seen_numbers = set(), set()
        for selected in self.targets or []:
            target = selected.target
            if target is not None:
                key = _reference_key(target)
                if key in seen_targets:
                    logger.error(f'Target {target.name} is selected more than once.')
                seen_targets.add(key)
                selected.material = target.material
                selected.manufacturer = target.manufacturer
                selected.purchase_date = target.purchase_date
            if selected.target_number is not None:
                if selected.target_number in seen_numbers:
                    logger.warning(
                        f'Target number {selected.target_number} is used twice.'
                    )
                seen_numbers.add(selected.target_number)

    def _normalize_substrates(self, archive: EntryArchive, logger: BoundLogger):
        seen = set()
        for new in self.substrates or []:
            new.sample_user_id = (
                sample_user_id(
                    self.pvd_system, self.datetime, new.run_number, new.sample_number
                )
                or new.sample_user_id
            )
            if not new.sample_uuid:
                new.sample_uuid = str(uuid.uuid4())
            if new.sample_user_id is not None:
                if new.sample_user_id in seen:
                    logger.warning(f'Substrate {new.sample_user_id} is defined twice.')
                seen.add(new.sample_user_id)
            if new.substrate is None and new.sample_user_id:
                new.substrate = self._create_substrate_entry(new, archive)

    def _create_substrate_entry(self, new: NewSubstrate, archive: EntryArchive):
        if archive is None or archive.m_context is None or archive.metadata is None:
            return None
        if not archive.metadata.upload_id:
            return None
        from nomad_material_processing.utils import create_archive

        file_name = re.sub(r'[^\w.-]', '_', new.sample_user_id) + '.archive.json'
        return create_archive(
            new.to_substrate(self.pvd_system, self.datetime), archive, file_name
        )

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
        substrate = loader.substrate
        if substrate is None:
            substrate = next(
                (new.substrate for new in self.substrates or [] if new.substrate),
                None,
            )
        sub_sections = self.m_def.all_sub_sections
        if not self.targets:
            for selected in recipe.targets or []:
                self.m_add_sub_section(sub_sections['targets'], _copy(selected))
        for step in recipe.steps or []:
            copied = _copy(step)
            if isinstance(copied, PLDDepositionStep):
                copied.substrate = substrate
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


class SAPLDLogbook(PLDLogbook):
    """Electronic lab notebook of an SA-PLD run."""

    m_def = Section(label='SA-PLD Logbook')
    pvd_system = Quantity(
        type=str,
        default='SA-PLD',
        description='Read-only: fixed by the logbook type.',
    )
    substrate_carrier = Quantity(
        type=MEnum('Omicron carrier', '1" carrier'),
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
        type=MEnum(
            'Omicron carrier', '1" carrier', '4" wafer carrier', 'Sample select carrier'
        ),
        a_eln=ELNAnnotation(component=ELNComponentEnum.EnumEditQuantity),
    )
    particle_reduction_plate = Quantity(
        type=MEnum('in use', 'not in use'),
        a_eln=ELNAnnotation(component=ELNComponentEnum.RadioEnumEditQuantity),
    )
    steps = SubSection(section_def=LAPLDStep, repeats=True)
