from typing import Optional

from nomad.config.models.plugins import SchemaPackageEntryPoint
from pydantic import Field


class PLD4ESchemasEntryPoint(SchemaPackageEntryPoint):
    database_upload_id: Optional[str] = Field(  # noqa: UP045 (Python 3.9)
        None,
        description=(
            'The upload that holds the target and substrate database. Make the '
            'maintainers its coauthors and everyone else a reviewer: logbooks '
            'and samples only choose targets and substrates from this upload.'
        ),
    )

    def load(self):
        from differ_pld4e_schemas.schema_packages.schema_package import m_package

        return m_package


schema_package_entry_point = PLD4ESchemasEntryPoint(
    name='PLD4Energy Schemas',
    description='Schemas for the SA-PLD, LA-PLD and SPS logbooks, their samples, '
    'targets and substrates, and the in-situ techniques.',
)
