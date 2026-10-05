"""Runtime validation entry points for the pilot fixture pack."""
from typing import Any, Tuple

from pydantic import ValidationError

from app.pilot.models import ExpectedReference, PilotManifest


def validate_manifest(data: dict[str, Any]) -> PilotManifest:
    return PilotManifest.model_validate(data)


def try_validate_manifest(
    data: dict[str, Any],
) -> Tuple[PilotManifest | None, ValidationError | None]:
    try:
        return PilotManifest.model_validate(data), None
    except ValidationError as exc:
        return None, exc


def validate_expected_reference(data: dict[str, Any]) -> ExpectedReference:
    return ExpectedReference.model_validate(data)


def try_validate_expected_reference(
    data: dict[str, Any],
) -> Tuple[ExpectedReference | None, ValidationError | None]:
    try:
        return ExpectedReference.model_validate(data), None
    except ValidationError as exc:
        return None, exc
