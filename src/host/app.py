from src.application.web import WebService
from src.infrastructure.di.bootstrap import bootstrap_di
from src.infrastructure.di.inject import resolve
from src.infrastructure.observability.logging_config import configure_logging
from src.infrastructure.providers.runtime.runtime_settings import RuntimeSettings


bootstrap_di()
runtime_settings = resolve(RuntimeSettings)
configure_logging(runtime_settings.log_level)
app = resolve(WebService).create_app()
