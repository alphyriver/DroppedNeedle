"""Pure dynamic naming selection for Library Management paths."""

from api.v1.schemas.library_management import (
    LibraryManagementRootAssignment,
    NamingScriptSettings,
)
from core.exceptions import ValidationError
from models.library_management_canonical import (
    CanonicalReleaseDocument,
    CanonicalTrackDocument,
)
from models.library_management_planning import (
    ManagementNamingContext,
    PinnedLibraryManagementProfile,
    naming_policy_revision,
)


def select_naming_script(
    pinned: PinnedLibraryManagementProfile,
    organization_audio_medium_count: int,
) -> NamingScriptSettings:
    if (
        organization_audio_medium_count > 1
        and pinned.multi_disc_naming_script is not None
    ):
        return pinned.multi_disc_naming_script
    return pinned.naming_script


def management_naming_context(
    release: CanonicalReleaseDocument,
    track: CanonicalTrackDocument,
) -> ManagementNamingContext:
    if track.disc_number < 1:
        raise ValidationError(
            "A mapped MusicBrainz track needs a valid medium position for naming."
        )
    return ManagementNamingContext(
        album_disambiguation=release.album_disambiguation,
        medium_format=(track.media_format or "").strip(),
        medium_number=track.disc_number,
        organization_audio_medium_count=release.organization_audio_medium_count,
    )


def activation_naming_policy_matches(
    assignment: LibraryManagementRootAssignment,
    pinned: PinnedLibraryManagementProfile,
) -> bool:
    expected = naming_policy_revision(pinned)
    if assignment.activation_naming_policy_revision is not None:
        return assignment.activation_naming_policy_revision == expected
    return pinned.multi_disc_naming_script is None
