from nomad.config.models.plugins import SchemaPackageEntryPoint


class PLD4ESchemasEntryPoint(SchemaPackageEntryPoint):
    def load(self):
        from differ_pld4e_schemas.schema_packages.schema_package import m_package

        return m_package


schema_package_entry_point = PLD4ESchemasEntryPoint(
    name='PLD4Energy Schemas',
    description='Schemas for the SA-PLD, LA-PLD and SPS logbooks, their samples, '
    'targets and substrates, and the in-situ techniques.',
)
