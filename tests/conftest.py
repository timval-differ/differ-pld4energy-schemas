from nomad.config import config

from differ_pld4e_schemas.database import ENTRY_POINT_ID

# The upload of the target and substrate database in the tests. Set before the
# test modules build the dashboards' form definitions, which include it.
DATABASE_UPLOAD = 'target_db'

config.load_plugins()
config.get_plugin_entry_point(ENTRY_POINT_ID).database_upload_id = DATABASE_UPLOAD
