"""
What the logbooks add to the native NOMAD process (`PulsedLaserDeposition`,
`SputterDeposition`): the operator of the run, and a name when none is given.
"""

from __future__ import annotations

from nomad.datamodel.data import ArchiveSection
from nomad.datamodel.metainfo.annotations import ELNAnnotation, ELNComponentEnum
from nomad.metainfo import Quantity, Section

from differ_pld4e_schemas import m_package

__all__ = ['RunDetails', 'm_package']


class RunDetails(ArchiveSection):
    """Who carried out a run. Mixed into a native process."""

    m_def = Section()
    operator_name = Quantity(
        type=str,
        description='The person who carried out the process.',
        a_eln=ELNAnnotation(component=ELNComponentEnum.StringEditQuantity),
    )
    operator_email = Quantity(
        type=str,
        a_eln=ELNAnnotation(component=ELNComponentEnum.StringEditQuantity),
    )

    def default_name(self, system: str) -> None:
        """
        `<system> <yyyy-mm-dd hh:mm>` for a run without a name; it also names
        the entry. (NOMAD would otherwise take the entry name, which may not
        be set yet.)
        """
        if not self.name and self.datetime is not None:
            self.name = f'{system} {self.datetime:%Y-%m-%d %H:%M}'
