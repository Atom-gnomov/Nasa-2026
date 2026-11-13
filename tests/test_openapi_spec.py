"""contracts/openapi.yaml — коректна специфікація OpenAPI 3.1 (структура, посилання $ref)."""

from pathlib import Path

import pytest
import yaml

openapi_spec_validator = pytest.importorskip("openapi_spec_validator")

SPEC = Path(__file__).resolve().parent.parent / "contracts" / "openapi.yaml"


def test_openapi_spec_is_valid():
    openapi_spec_validator.validate(yaml.safe_load(SPEC.read_text(encoding="utf-8")))
