"""OCS / openDesktop / Pling integration helpers."""

from conkystudio.store.ocs_client import (
    DEFAULT_PROVIDERS,
    OcsCategory,
    OcsClient,
    OcsContent,
    OcsDownload,
    OcsError,
    OcsNotFound,
    OcsRateLimited,
    provider_base,
)
from conkystudio.store.ocs_handler import (
    OcsLocalServer,
    consume_argv_ocs_urls,
    handle_ocs_url,
    install_content,
    is_ocs_url,
    try_forward_to_running_instance,
)
from conkystudio.store.ocs_url import OcsUrl, OcsUrlError, build_ocs_url, parse_ocs_url
from conkystudio.store.ocs_install import InstallResult, install_from_ocs_url, install_from_url

__all__ = [
    "DEFAULT_PROVIDERS",
    "InstallResult",
    "OcsCategory",
    "OcsClient",
    "OcsContent",
    "OcsDownload",
    "OcsError",
    "OcsLocalServer",
    "OcsNotFound",
    "OcsRateLimited",
    "OcsUrl",
    "OcsUrlError",
    "build_ocs_url",
    "consume_argv_ocs_urls",
    "handle_ocs_url",
    "install_content",
    "install_from_ocs_url",
    "install_from_url",
    "is_ocs_url",
    "parse_ocs_url",
    "provider_base",
    "try_forward_to_running_instance",
]
