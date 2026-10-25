"""Exception hierarchy of the przepisnik tool."""


class PrzepisnikError(Exception):
    """Base class for all expected, user-facing errors."""


class SourceReadError(PrzepisnikError):
    """A source document could not be opened or read."""


class UnsupportedSourceError(PrzepisnikError):
    """No parser recognised the source document."""


class SourceAlreadyImportedError(PrzepisnikError):
    """The same source file (by content hash) was imported before."""


class StoreError(PrzepisnikError):
    """The recipe store contains invalid data or cannot be written."""


class DraftError(PrzepisnikError):
    """A recipe draft file is missing or does not match the schema."""
