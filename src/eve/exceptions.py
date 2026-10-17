"""Application exception types."""


class EveError(Exception):
    """Base class for Project EVE errors that should be shown to the user."""


class RendererUnavailable(EveError):
    """The 3D renderer could not be initialised (no OpenGL, driver problem...)."""


class AlreadyRunning(EveError):
    """Another instance of Project EVE is already running for this user."""
