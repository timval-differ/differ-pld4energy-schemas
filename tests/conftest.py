from helpers import DATABASE_UPLOAD
from nomad.config import config

from differ_pld4e_schemas.database import ENTRY_POINT_ID

# Set the database upload before the test modules build the dashboards' form
# definitions, which include it.

config.load_plugins()
config.get_plugin_entry_point(ENTRY_POINT_ID).database_upload_id = DATABASE_UPLOAD
