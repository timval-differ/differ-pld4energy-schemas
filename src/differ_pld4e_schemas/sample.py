"""
Samples, independent of the system they are made or processed in.

A substrate is the template a film is grown on; a sample is the substrate with
the films grown on it. Every run (a PLD logbook now, a sputter run later) starts
by listing the samples it makes or processes, with `SampleRun`.

The kinds of substrate in use (e.g. SrTiO3 10x10 mm) are kept in a database of
`SubstrateType` entries, like the targets, so new ones can be added without a
code change. A film refers to the target it is grown from, which gives its
material.

The sections are native NOMAD ones (nomad-material-processing): a substrate type
is a `CrystallineSubstrate`, a film a `ThinFilm` and a sample a
`CompositeSystem`. Their elements come from the chemical formulas of the
substrate and the targets, so NOMAD's search finds samples by element.
"""

from __future__ import annotations

import re
import uuid
from typing import TYPE_CHECKING

from nomad.datamodel.data import ArchiveSection, EntryData
from nomad.datamodel.metainfo.annotations import ELNAnnotation, ELNComponentEnum
from nomad.datamodel.metainfo.basesections import (
    CompositeSystem,
    CompositeSystemReference,
    SystemComponent,
)
from nomad.metainfo import MEnum, Quantity, Reference, Section, SubSection
from nomad.metainfo.metainfo import MetainfoReferenceError
from nomad_material_processing.general import CrystallineSubstrate, ThinFilm

from differ_pld4e_schemas import m_package
from differ_pld4e_schemas.composition import (
    apply_formula,
    chemical_formula_quantity,
    elements_of,
)
from differ_pld4e_schemas.database import (
    check_database_entry,
    check_database_reference,
)
from differ_pld4e_schemas.target import GENERATED, Target, in_stock_quantity

if TYPE_CHECKING:
    from nomad.datamodel.datamodel import EntryArchive
    from structlog.stdlib import BoundLogger

__all__ = [
    'Layer',
    'Sample',
    'SampleInRun',
    'SampleRun',
    'SubstrateType',
    'm_package',
    'sample_id',
    'sample_name',
]

NEW_SAMPLE = 'New sample'
EXTERNAL_SAMPLE = 'External sample'
EXISTING_SAMPLE = 'Existing sample'
SAMPLE_ORIGINS = (NEW_SAMPLE, EXTERNAL_SAMPLE, EXISTING_SAMPLE)


def sample_id(system, start, number):
    """`{system}_{yyyy-mm-dd}_{hh:mm}_S{nn}`, or None while a part is missing."""
    if not system or start is None or not number:
        return None
    return f'{system}_{start:%Y-%m-%d_%H:%M}_S{int(number):02d}'


def _number_text(value) -> str:
    return f'{float(value):g}'


def sample_name(substrate_material, layers):
    """
    `Substrate_Film-<t>nm_Film-<n>p` from the substrate material and (material,
    thickness in nm[, number of pulses]) tuples. A film whose thickness is given
    as a number of pulses shows it as `<n>p`; layers without a material are
    left out.
    """
    if not substrate_material:
        return None
    parts = [substrate_material]
    for layer_material, thickness, *pulses in layers or []:
        if not layer_material:
            continue
        if thickness is not None:
            parts.append(f'{layer_material}-{_number_text(thickness)}nm')
        elif pulses and pulses[0] is not None:
            parts.append(f'{layer_material}-{_number_text(pulses[0])}p')
        else:
            parts.append(layer_material)
    return '_'.join(parts)


def file_name_for(text: str) -> str:
    return re.sub(r'[^\w.-]', '_', text) + '.archive.json'


def resolved(reference, *names):
    """Values of a referenced section, or Nones if it cannot be resolved."""
    if reference is None:
        return (None,) * len(names)
    try:
        return tuple(getattr(reference, name, None) for name in names)
    except MetainfoReferenceError:  # NOMAD reports the reference itself
        return (None,) * len(names)


def _resolvable(reference) -> bool:
    return resolved(reference, 'm_def') != (None,)


def _layer_pairs(layers):
    return [
        (
            layer.material,
            layer.thickness.to('nm').magnitude if layer.thickness is not None else None,
            layer.number_of_pulses,
        )
        for layer in layers or []
    ]


class SubstrateType(CrystallineSubstrate, EntryData):
    """
    A kind of substrate in the substrate database, e.g. SrTiO3 10x10 mm. Samples
    refer to it. Maintainers add an entry for every kind of substrate in use, in
    the target and substrate database upload.
    """

    m_def = Section(
        label='Substrate type',
        a_display={
            'visible': {'exclude': GENERATED},
            'order': [
                'name',
                'material',
                'chemical_formula',
                'size',
                'supplier',
                'supplier_id',
                'lab_id',
                'in_stock',
                'description',
            ],
        },
    )
    name = Quantity(
        type=str,
        description='Display name. Defaults to the material and size.',
        a_eln=ELNAnnotation(component=ELNComponentEnum.StringEditQuantity),
    )
    material = Quantity(
        type=str,
        description='Substrate material as named in the lab, e.g. SrTiO3 or Si. '
        'Used in sample names.',
        a_eln=ELNAnnotation(component=ELNComponentEnum.StringEditQuantity),
    )
    chemical_formula = chemical_formula_quantity()
    size = Quantity(
        type=str,
        description='e.g. 10x10 mm or 1" with flat.',
        a_eln=ELNAnnotation(component=ELNComponentEnum.StringEditQuantity),
    )
    in_stock = in_stock_quantity()

    def normalize(self, archive: EntryArchive, logger: BoundLogger) -> None:
        if not self.name and self.material:
            self.name = ' '.join(part for part in (self.material, self.size) if part)
        check_database_entry(archive, logger, 'substrate type')
        apply_formula(self, archive, logger)
        super().normalize(archive, logger)


class Layer(ThinFilm):
    """
    A film grown on the sample, from one of the targets. Its elements are those
    of the target, so the sample (and the run) can be found by them.
    """

    m_def = Section(label_quantity='material')
    material = Quantity(
        type=str,
        description='Film material. Taken from the target if empty.',
        a_eln=ELNAnnotation(component=ELNComponentEnum.StringEditQuantity),
    )
    thickness = Quantity(
        type=float,
        unit='m',
        description='Intended thickness of the film.',
        a_eln=ELNAnnotation(
            component=ELNComponentEnum.NumberEditQuantity, defaultDisplayUnit='nm'
        ),
    )
    number_of_pulses = Quantity(
        type=int,
        description='Intended thickness of the film as a number of laser pulses, '
        'when it is not given in nm.',
        a_eln=ELNAnnotation(component=ELNComponentEnum.NumberEditQuantity),
    )
    target = Quantity(
        type=Reference(Target.m_def),
        description='The target the film is grown from.',
        a_eln=ELNAnnotation(component=ELNComponentEnum.ReferenceEditQuantity),
    )

    def normalize(self, archive: EntryArchive, logger: BoundLogger) -> None:
        if not self.material:
            (self.material,) = resolved(self.target, 'material')
        self.name = self.name or self.material
        if _resolvable(self.target):
            self.elemental_composition = elements_of(self.target)
        super().normalize(archive, logger)


class _SampleDetails(ArchiveSection):
    """What a sample and its entry in a run have in common."""

    m_def = Section()
    sample_id = Quantity(
        type=str,
        description='Generated as {system}_{yyyy-mm-dd}_{hh:mm}_S{nn}.',
    )
    sample_uuid = Quantity(
        type=str,
        description='Read-only: generated unique identifier, e.g. for a QR code label.',
    )
    origin = Quantity(
        type=MEnum(*SAMPLE_ORIGINS),
        a_eln=ELNAnnotation(component=ELNComponentEnum.EnumEditQuantity),
    )
    substrate = Quantity(
        type=Reference(SubstrateType.m_def),
        description='The kind of substrate, from the substrate database.',
        a_eln=ELNAnnotation(component=ELNComponentEnum.ReferenceEditQuantity),
    )
    substrate_details = Quantity(
        type=str,
        description='Substrate of an external sample that is not in the database.',
        a_eln=ELNAnnotation(component=ELNComponentEnum.StringEditQuantity),
    )
    substrate_material = Quantity(
        type=str,
        description='Read-only: taken from the substrate.',
    )
    substrate_size = Quantity(
        type=str,
        description='Read-only: taken from the substrate.',
    )
    substrate_batch_number = Quantity(
        type=str,
        description='Batch number of the substrate, as given by the supplier.',
        a_eln=ELNAnnotation(component=ELNComponentEnum.StringEditQuantity),
    )
    layers = SubSection(section_def=Layer, repeats=True)

    def _copy_substrate_and_films(self) -> None:
        """Material and size from the substrate, film materials from the targets."""
        material, size = resolved(self.substrate, 'material', 'size')
        if material:
            self.substrate_material, self.substrate_size = material, size
        elif self.substrate is None and self.substrate_details:
            self.substrate_material = self.substrate_material or self.substrate_details
        for layer in self.layers or []:
            if not layer.material:
                (layer.material,) = resolved(layer.target, 'material')

    def _generated_name(self):
        return sample_name(self.substrate_material, _layer_pairs(self.layers))


class Sample(CompositeSystem, _SampleDetails, EntryData):
    """
    A sample: a substrate with the films grown on it. One entry per sample, so
    processes and measurements of any system can refer to it. Its elements are
    those of the substrate (a component) and of the films.
    """

    m_def = Section(
        label='Sample',
        label_quantity='sample_id',
        a_display={'visible': {'exclude': GENERATED}},
    )
    system = Quantity(
        type=str,
        description='The system the sample was made in, e.g. SA-PLD.',
        a_eln=ELNAnnotation(component=ELNComponentEnum.StringEditQuantity),
    )

    def normalize(self, archive: EntryArchive, logger: BoundLogger) -> None:
        if not self.sample_uuid:
            self.sample_uuid = str(uuid.uuid4())
        check_database_reference(self.substrate, archive, logger, 'substrate')
        self._copy_substrate_and_films()
        if not self.name:
            self.name = self._generated_name()
        if self.sample_id and not self.lab_id:
            self.lab_id = self.sample_id
        self.components = (
            [SystemComponent(name=self.substrate_material, system=self.substrate)]
            if _resolvable(self.substrate)
            else []
        )
        super().normalize(archive, logger)
        if self.sample_id and archive is not None and archive.metadata is not None:
            archive.metadata.entry_name = self.sample_id


class SampleInRun(_SampleDetails, CompositeSystemReference):
    """
    A sample made or processed in a run. A new or external sample gets its own
    Sample entry on save, linked in `reference`; an existing sample is selected
    there. `layers` are the films grown in this run; the dashboard takes them
    from the deposition steps. An external sample may already carry films:
    those are `prior_layers`.
    """

    m_def = Section(label_quantity='sample_id')
    name = Quantity(
        type=str,
        description='Generated as Substrate_Film-thickness_Film-thickness.',
        a_eln=ELNAnnotation(component=ELNComponentEnum.StringEditQuantity),
    )
    comments = Quantity(
        type=str,
        a_eln=ELNAnnotation(component=ELNComponentEnum.RichTextEditQuantity),
    )
    reference = Quantity(
        type=Reference(Sample.m_def),
        description='The Sample entry of this sample.',
        a_eln=ELNAnnotation(
            component=ELNComponentEnum.ReferenceEditQuantity, label='Sample'
        ),
    )
    prior_layers = SubSection(
        section_def=Layer,
        repeats=True,
        description='Films already on an external sample, from the substrate up.',
    )

    def _generated_name(self):
        layers = [*(self.prior_layers or []), *(self.layers or [])]
        return sample_name(self.substrate_material, _layer_pairs(layers))

    def to_sample(self, system, start) -> Sample:
        sample = Sample(
            name=self.name,
            datetime=start,
            description=self.comments,
            system=system,
            sample_id=self.sample_id,
            sample_uuid=self.sample_uuid,
            origin=self.origin,
            substrate=self.substrate,
            substrate_details=self.substrate_details,
            substrate_material=self.substrate_material,
            substrate_size=self.substrate_size,
            substrate_batch_number=self.substrate_batch_number,
        )
        # The Sample entry has the whole stack: the films it came with first.
        for layer in [*(self.prior_layers or []), *(self.layers or [])]:
            sample.layers.append(
                Layer(
                    material=layer.material,
                    thickness=layer.thickness,
                    number_of_pulses=layer.number_of_pulses,
                    target=layer.target,
                )
            )
        return sample


class SampleRun(ArchiveSection):
    """
    A run that starts from the samples it makes or processes. Mixed into a
    native process, whose `samples` it specialises.
    """

    m_def = Section()
    samples = SubSection(section_def=SampleInRun, repeats=True)

    def _normalize_samples(
        self, archive: EntryArchive, logger: BoundLogger, system, start
    ) -> None:
        seen, number = set(), 0
        for item in self.samples or []:
            if not item.sample_uuid:
                item.sample_uuid = str(uuid.uuid4())
            if item.origin == EXISTING_SAMPLE:
                self._copy_existing(item)
            else:
                number += 1
                check_database_reference(item.substrate, archive, logger, 'substrate')
                item.sample_id = item.sample_id or sample_id(system, start, number)
                item._copy_substrate_and_films()
                if not item.name:
                    item.name = item._generated_name()
            if item.sample_id is not None:
                if item.sample_id in seen:
                    logger.warning(f'Sample {item.sample_id} is listed twice.')
                seen.add(item.sample_id)
            if item.origin == EXISTING_SAMPLE:
                if item.reference is None:
                    logger.warning('Select the existing sample.')
            elif item.reference is None and item.sample_id:
                item.reference = self._create_sample_entry(item, archive, system, start)
            # The sample ID, as on the Sample entry. Only set once the entry is
            # linked: without a link NOMAD would look the entry up by it.
            if item.reference is not None and item.sample_id:
                item.lab_id = item.sample_id

    @staticmethod
    def _copy_existing(item: SampleInRun) -> None:
        sample_id_, name = resolved(item.reference, 'sample_id', 'name')
        item.sample_id = item.sample_id or sample_id_
        item.name = item.name or name

    @staticmethod
    def _create_sample_entry(item: SampleInRun, archive: EntryArchive, system, start):
        if archive is None or archive.m_context is None or archive.metadata is None:
            return None
        if not archive.metadata.upload_id:
            return None
        from nomad_material_processing.utils import create_archive

        return create_archive(
            item.to_sample(system, start), archive, file_name_for(item.sample_id)
        )
