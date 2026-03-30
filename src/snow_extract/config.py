from dataclasses import dataclass, field
from pathlib import Path
from dotenv import load_dotenv
import os

load_dotenv()

@dataclass
class SnowConfig:
    instance_url: str = field(default_factory=lambda: os.getenv("SNOW_INSTANCE_URL", ""))
    username: str = field(default_factory=lambda: os.getenv("SNOW_USERNAME", ""))
    password: str = field(default_factory=lambda: os.getenv("SNOW_PASSWORD", ""))
    export_fields: str = field(default_factory=lambda: os.getenv("SNOW_EXPORT_FIELDS", "sys_id,number,short_description,priority,urgency,impact,state,category,subcategory,opened_at,resolved_at,closed_at,location,cmdb_ci,assignment_group,sys_updated_on"))
    export_start_date: str = field(default_factory=lambda: os.getenv("SNOW_EXPORT_START_DATE", "2024-01-01"))
    data_dir: Path = field(default_factory=lambda: Path(os.getenv("DATA_DIR", "./data")))

@dataclass
class GrafanaConfig:
    url: str = field(default_factory=lambda: os.getenv("GRAFANA_URL", ""))
    api_token: str = field(default_factory=lambda: os.getenv("GRAFANA_API_TOKEN", ""))
    prometheus_ds_id: str = field(default_factory=lambda: os.getenv("GRAFANA_PROMETHEUS_DS_ID", "1"))

    @property
    def is_configured(self) -> bool:
        return bool(self.url and self.api_token)

@dataclass
class NetBoxConfig:
    url: str = field(default_factory=lambda: os.getenv("NETBOX_URL", ""))
    token: str = field(default_factory=lambda: os.getenv("NETBOX_TOKEN", ""))

    @property
    def is_configured(self) -> bool:
        return bool(self.url and self.token)
