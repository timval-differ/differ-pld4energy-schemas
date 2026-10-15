from nomad.config.models.plugins import SchemaPackageEntryPoint


class SputterSchemasEntryPoint(SchemaPackageEntryPoint):
    def load(self):
        from differ_pld4e_schemas.schema_packages.schema_package import m_package

        return m_package


schema_package_entry_point = SputterSchemasEntryPoint(
    name='Sputter Deposition Schemas',
    description='Schemas for sputter deposition processes and thin-film samples.',
)
