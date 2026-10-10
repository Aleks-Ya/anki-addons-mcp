import argparse
import logging
import sys
from typing import Any

from anki_addons_mcp import __version__
from anki_addons_mcp.bootstrap import create_app
from anki_addons_mcp.config import Settings


def _parse_args(argv: list[str] | None) -> dict[str, Any]:
    parser = argparse.ArgumentParser(prog="anki-addons-mcp", description="MCP server for the Anki Addons dataset")
    parser.add_argument("--version", action="version", version=__version__)
    parser.add_argument("--transport", choices=["stdio", "http"])
    parser.add_argument("--host")
    parser.add_argument("--port", type=int)
    parser.add_argument("--path")
    parser.add_argument("--backend", choices=["hf_parquet", "local_parquet"])
    parser.add_argument("--data-dir", dest="data_dir")
    parser.add_argument("--cache-dir", dest="cache_dir")
    parser.add_argument("--hf-revision", dest="hf_revision")
    parser.add_argument("--refresh-interval", dest="refresh_interval_seconds", type=int)
    parser.add_argument("--no-sql", dest="sql_enabled", action="store_const", const=False)
    parser.add_argument("--log-level", dest="log_level", choices=["DEBUG", "INFO", "WARNING", "ERROR"])
    return {k: v for k, v in vars(parser.parse_args(argv)).items() if v is not None}


def _run_http(mcp: Any, settings: Settings) -> None:
    import uvicorn
    from mcp.server.transport_security import TransportSecuritySettings

    security = None
    if settings.allowed_hosts:
        security = TransportSecuritySettings(enable_dns_rebinding_protection=True,
                                             allowed_hosts=settings.allowed_hosts)
    app = mcp.streamable_http_app(streamable_http_path=settings.path, json_response=True, stateless_http=True,
                                  host=settings.host, transport_security=security)
    uvicorn.run(app, host=settings.host, port=settings.port, log_level=settings.log_level.lower())


def main(argv: list[str] | None = None) -> None:
    settings = Settings(**_parse_args(argv))
    logging.basicConfig(stream=sys.stderr, level=settings.log_level,
                        format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    if settings.log_level != "DEBUG":
        for noisy in ("httpx", "httpx2", "huggingface_hub"):
            logging.getLogger(noisy).setLevel(logging.WARNING)
    mcp, _ = create_app(settings)
    if settings.transport == "http":
        _run_http(mcp, settings)
    else:
        mcp.run("stdio")


if __name__ == "__main__":
    main()
