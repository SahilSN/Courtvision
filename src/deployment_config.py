"""Explicit hosting scope; local full-feature behavior remains the default."""

import os


def get_deployment_profile(environ=None):
    environ = os.environ if environ is None else environ
    profile = environ.get("COURTVISION_DEPLOYMENT_PROFILE", "full").strip().lower()
    if profile not in {"full", "published"}:
        raise ValueError(
            "COURTVISION_DEPLOYMENT_PROFILE must be 'full' or 'published'."
        )
    return profile


def navigation_modes(profile):
    if profile == "published":
        return ["Season Intelligence"]
    if profile == "full":
        return ["Live", "Season Intelligence", "Historical"]
    raise ValueError(f"Unknown deployment profile: {profile!r}")
