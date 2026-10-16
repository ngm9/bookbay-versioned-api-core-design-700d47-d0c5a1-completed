import logging
import os
import sys

SERVICE_NAME = "Bookbay API"
SERVICE_VERSION = "1.18.0"
OPENAPI_DESCRIPTION = "Public API used by Bookbay mobile clients and marketplace operations."
OPENAPI_TAGS = [
    {"name": "users", "description": "User profiles and addresses"},
    {"name": "orders", "description": "Carts, checkout, payments, and orders"},
    {"name": "listings", "description": "Second-hand textbook listings"},
    {"name": "search", "description": "Catalog discovery"},
    {"name": "refunds", "description": "Cancellation and refund operations"},
]


def configure_logging() -> None:
    level_name = os.getenv("LOG_LEVEL", "INFO").upper()
    level = getattr(logging, level_name, logging.INFO)
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(
        logging.Formatter(
            "%(asctime)s level=%(levelname)s logger=%(name)s message=%(message)s"
        )
    )
    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(level)


def application_metadata() -> dict[str, object]:
    return {
        "title": SERVICE_NAME,
        "version": SERVICE_VERSION,
        "description": OPENAPI_DESCRIPTION,
        "openapi_tags": OPENAPI_TAGS,
    }
