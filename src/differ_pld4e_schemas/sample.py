"""
Samples, independent of the system they are made or processed in.

A substrate is the template a film is grown on; a sample is the substrate with
the films grown on it. Every run (a PLD logbook now, a sputter run later) starts
by listing the samples it makes or processes, with `SampleRun`.
"""

from __future__ import annotations

import re
import uuid
from typing import TYPE_CHECKING

from nomad.datamodel.data import ArchiveSection, EntryData
from nomad.datamodel.metainfo.annotations import ELNAnnotation, ELNComponentEnum
from nomad.datamodel.metainfo.basesections import CompositeSystem
from nomad.metainfo import MEnum, Quantity, Reference, Section, SubSection
from nomad.metainfo.metainfo import MetainfoReferenceError

from differ_pld4e_schemas import m_package
from differ_pld4e_schemas.target import Target

if TYPE_CHECKING:
    from nomad.datamodel.datamodel import EntryArchive
    from structlog.stdlib import BoundLogger

__all__ = [
    'Layer',
    'Sample',
    'SampleInRun',
    'SampleRun',
    'm_package',
    'sample_id',
    'sample_name',
]

# Substrate type -> (material, size).
SUBSTRATE_TYPES = {
    'SrTiO3 10x10 mm': ('SrTiO3', '10x10 mm'),
    'Si 1" with flat': ('Si', '1" with flat'),
    'Si 1" without flat': ('Si', '1" without flat'),
    'glass': ('glass', None),
    'FTO': ('FTO', None),
}
OTHER_SUBSTRATE = 'Other'
NEW_SAMPLE = 'New sample'
EXTERNAL_SAMPLE = 'External sample'
EXISTING_SAMPLE = 'Existing sample'
SAMPLE_ORIGINS = (NEW_SAMPLE, EXTERNAL_SAMPLE, EXISTING_SAMPLE)


def sample_id(system, start, number):
    """`{system}_{yyyy-mm-dd}_{hh:mm}_S{nn}`, or None while a part is missing."""
    if not system or start is None or not number:
        return None
    return f'{system}_{start:%Y-%m-%d_%H:%M}_S{int(number):02d}'


def substrate_material(substrate, substrate_details=None):
    if substrate in SUBSTRATE_TYPES:
        return SUBSTRATE_TYPES[substrate][0]
    return substrate_details or None


def _number_text(value) -> str:
    return f'{float(value):g}'


def sample_name(substrate, layers, substrate_details=None):
    """
    `Substrate_Film-<t>nm_Film-<t>nm` from the substrate and (material, thickness
    in nm) pairs; layers without a material are left out.
    """
    material = substrate_material(substrate, substrate_details)
    if not material:
        return None
    parts = [material]
    for layer_material, thickness in layers or []:
        if not layer_material:
            continue
        if thickness is None:
            parts.append(layer_material)
        else:
            parts.append(f'{layer_material}-{_number_text(thickness)}nm')
    return '_'.join(parts)


def file_name_for(text: str) -> str:
    return re.sub(r'[^\w.-]', '_', text) + '.archive.json'


def _layer_pairs(layers):
    return [
        (
            layer.material,
            layer.thickness.to('nm').magnitude if layer.thickness is not None else None,
        )
        for layer in layers or []
    ]


class Layer(ArchiveSection):
    """A film grown on the sample."""

    m_def = Section(label_quantity='material')
    material = Quantity(
        type=str,
        description='Film material, as named in the target database.',
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
    target = Quantity(
        type=Reference(Target.m_def),
        description='Optional: the target the film is grown from.',
        a_eln=ELNAnnotation(component=ELNComponentEnum.ReferenceEditQuantity),
    )


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
        type=MEnum(*SUBSTRATE_TYPES, OTHER_SUBSTRATE),
        a_eln=ELNAnnotation(component=ELNComponentEnum.EnumEditQuantity),
    )
    substrate_details = Quantity(
        type=str,
        description='Substrate of an external sample, if it is not in the list.',
        a_eln=ELNAnnotation(component=ELNComponentEnum.StringEditQuantity),
    )
    layers = SubSection(section_def=Layer, repeats=True)


class Sample(CompositeSystem, _SampleDetails, EntryData):
    """
    A sample: a substrate with the films grown on it. One entry per sample, so
    processes and measurements of any system can refer to it.
    """

    m_def = Section(label='Sample', label_quantity='sample_id')
    system = Quantity(
        type=str,
        description='The system the sample was made in, e.g. SA-PLD.',
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

    def normalize(self, archive: EntryArchive, logger: BoundLogger) -> None:
        if not self.sample_uuid:
            self.sample_uuid = str(uuid.uuid4())
        self.substrate_material = substrate_material(
            self.substrate, self.substrate_details
        )
        if self.substrate in SUBSTRATE_TYPES:
            self.substrate_size = SUBSTRATE_TYPES[self.substrate][1]
        if not self.name:
            self.name = sample_name(
                self.substrate, _layer_pairs(self.layers), self.substrate_details
            )
        if self.sample_id and not self.lab_id:
            self.lab_id = self.sample_id
        super().normalize(archive, logger)
        if self.sample_id and archive is not None and archive.metadata is not None:
            archive.metadata.entry_name = self.sample_id


class SampleInRun(_SampleDetails):
    """
    A sample made or processed in a run. A new or external sample gets its own
    Sample entry on save, linked in `sample`; an existing sample is selected
    there. `layers` are the films grown in this run.
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
    sample = Quantity(
        type=Reference(Sample.m_def),
        description='The Sample entry of this sample.',
        a_eln=ELNAnnotation(component=ELNComponentEnum.ReferenceEditQuantity),
    )

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
        )
        for layer in self.layers or []:
            sample.layers.append(
                Layer(
                    material=layer.material,
                    thickness=layer.thickness,
                    target=layer.target,
                )
            )
        return sample


class SampleRun(ArchiveSection):
    """A run that starts from the samples it makes or processes."""

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
                item.sample_id = item.sample_id or sample_id(system, start, number)
                if not item.name:
                    item.name = sample_name(
                        item.substrate,
                        _layer_pairs(item.layers),
                        item.substrate_details,
                    )
            if item.sample_id is not None:
                if item.sample_id in seen:
                    logger.warning(f'Sample {item.sample_id} is listed twice.')
                seen.add(item.sample_id)
            if item.origin == EXISTING_SAMPLE:
                if item.sample is None:
                    logger.warning('Select the existing sample.')
            elif item.sample is None and item.sample_id:
                item.sample = self._create_sample_entry(item, archive, system, start)

    @staticmethod
    def _copy_existing(item: SampleInRun) -> None:
        if item.sample is None:
            return
        try:
            item.sample_id = item.sample_id or item.sample.sample_id
            item.name = item.name or item.sample.name
        except MetainfoReferenceError:
            pass  # NOMAD reports the unresolvable reference itself

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
