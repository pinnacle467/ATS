"""Google Meet API v2beta helper — create a Meet Space with auto Gemini
smart notes + auto transcription enabled, so scheduled interviews
automatically get AI note-taking and transcript generation.

We use the v2beta variant because `ArtifactConfig.smartNotesConfig` and
`ArtifactConfig.transcriptionConfig` are exposed there. The v2 GA client
class does not surface `ArtifactConfig` as of google-apps-meet==0.5.0.

Fallback strategy is owned by the caller (routes_interviews.py): if this
function raises, the caller should still schedule the interview with a
plain Calendar-generated Meet link and surface a warning.
"""
from __future__ import annotations

import logging
from typing import Any

from google.apps import meet_v2beta
from google.oauth2.credentials import Credentials

logger = logging.getLogger(__name__)

# Scopes required to (a) create a Meet space and (b) set its artifact
# configuration (smart notes + transcription). If either of these is
# missing from the user's granted scopes, we skip the AI path entirely
# and let Calendar create a plain Meet link.
MEET_SPACE_CREATE_SCOPE = 'https://www.googleapis.com/auth/meetings.space.created'
MEET_SPACE_SETTINGS_SCOPE = 'https://www.googleapis.com/auth/meetings.space.settings'


def has_meet_ai_scopes(granted_scope_str: str) -> bool:
    granted = set((granted_scope_str or '').split())
    return MEET_SPACE_CREATE_SCOPE in granted and MEET_SPACE_SETTINGS_SCOPE in granted


def create_ai_meet_space(creds: Credentials) -> dict[str, Any]:
    """Create a Meet space with auto smart notes + transcription ON.

    Returns a dict with keys:
      - space_name:  e.g. "spaces/xyz-abc-uvw"  (full resource name)
      - meeting_uri: e.g. "https://meet.google.com/xxx-yyyy-zzz"
      - meeting_code: e.g. "xxx-yyyy-zzz"
      - ai_enabled: True if the response confirms both artifact configs are ON

    Raises whatever google.api_core / google.apps.meet exceptions occur.
    Typical failure modes:
      - PermissionDenied — scopes missing OR org policy blocks auto artifacts
      - FailedPrecondition — Workspace tier doesn't allow this feature
      - InvalidArgument — API contract mismatch
    """
    client = meet_v2beta.SpacesServiceClient(credentials=creds)

    AutoGen = meet_v2beta.SpaceConfig.ArtifactConfig.AutoGenerationType
    artifact_config = meet_v2beta.SpaceConfig.ArtifactConfig(
        smart_notes_config=meet_v2beta.SpaceConfig.ArtifactConfig.SmartNotesConfig(
            auto_smart_notes_generation=AutoGen.ON,
        ),
        transcription_config=meet_v2beta.SpaceConfig.ArtifactConfig.TranscriptionConfig(
            auto_transcription_generation=AutoGen.ON,
        ),
    )
    space = meet_v2beta.Space(
        config=meet_v2beta.SpaceConfig(artifact_config=artifact_config),
    )
    request = meet_v2beta.CreateSpaceRequest(space=space)
    resp = client.create_space(request=request)

    ai_enabled = False
    try:
        cfg = resp.config.artifact_config
        ai_enabled = (
            cfg.smart_notes_config.auto_smart_notes_generation == AutoGen.ON
            and cfg.transcription_config.auto_transcription_generation == AutoGen.ON
        )
    except Exception:  # noqa: BLE001
        ai_enabled = False

    result = {
        'space_name': resp.name,
        'meeting_uri': resp.meeting_uri,
        'meeting_code': resp.meeting_code,
        'ai_enabled': ai_enabled,
    }
    logger.info(
        'meet space created: uri=%s ai_enabled=%s', result['meeting_uri'], ai_enabled,
    )
    return result
