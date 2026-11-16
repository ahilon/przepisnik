"""Archive tested images and promote a verified pair without rebuilding them."""

import gzip
import json
import re
import shutil
from pathlib import Path
from typing import cast

from scripts.command_runner import CommandRunner
from scripts.release_policy import GIT_SHA, IMAGE_DIGEST, PACKAGE_VERSION

ARCHITECTURES = frozenset({"amd64", "arm64"})
REGISTRY_TIMEOUT_SECONDS = 900


def object_fields(value: object) -> dict[str, object]:
    """Require a string-keyed object at a JSON trust boundary.

    Args:
        value: Decoded JSON value.

    Returns:
        dict[str, object]: Validated object shape.

    Raises:
        ValueError: If the value is not a string-keyed object.
    """
    if not isinstance(value, dict) or any(not isinstance(key, str) for key in value):
        raise ValueError("Expected a JSON object")
    return cast(dict[str, object], value)


def validate_identity(image: str, architecture: str, revision: str, version: str) -> None:
    """Validate immutable image metadata before passing it to Docker.

    Args:
        image: Local image config digest.
        architecture: Supported target architecture.
        revision: Full Git commit SHA.
        version: Package release version.

    Returns:
        None: Every field has its expected shape.
    """
    if (
        not IMAGE_DIGEST.fullmatch(image)
        or architecture not in ARCHITECTURES
        or not GIT_SHA.fullmatch(revision)
        or not PACKAGE_VERSION.fullmatch(version)
    ):
        raise ValueError("Invalid image artifact identity")
    return None


def archive_image(
    image: str, architecture: str, revision: str, version: str, destination: Path
) -> None:
    """Export the exact local image used by smoke/E2E into a fresh CI artifact folder.

    Args:
        image: Tested local image ID, not a mutable tag.
        architecture: Expected target architecture.
        revision: Source Git SHA.
        version: Package version recorded in the image label.
        destination: New directory for compressed image and metadata.

    Returns:
        None: Saves an image archive and its identity together.
    """
    validate_identity(image, architecture, revision, version)
    runner = CommandRunner("docker", timeout=REGISTRY_TIMEOUT_SECONDS)
    info = object_fields(json.loads(runner.run(["image", "inspect", image]).stdout)[0])
    config = object_fields(info.get("Config"))
    labels = object_fields(config.get("Labels"))
    if (
        info.get("Id") != image
        or info.get("Os") != "linux"
        or info.get("Architecture") != architecture
        or labels.get("org.opencontainers.image.revision") != revision
        or labels.get("org.opencontainers.image.version") != version
    ):
        raise ValueError("Local image does not match tested release identity")
    destination.mkdir(parents=True, exist_ok=False)
    raw = destination / "image.tar"
    runner.run(["image", "save", "--output", str(raw), image])
    compressed = destination / "image.tar.gz"
    with raw.open("rb") as source, gzip.open(compressed, "wb", compresslevel=1) as target:
        shutil.copyfileobj(source, target)
    raw.unlink()
    metadata = {
        "image_id": image,
        "architecture": architecture,
        "revision": revision,
        "version": version,
    }
    (destination / "image.json").write_text(json.dumps(metadata), encoding="utf-8")
    return None


class ImagePublisher:
    """Publish only tested config IDs and keep version/commit tags immutable."""

    def __init__(self, repository: str, revision: str, version: str) -> None:
        """Validate the destination namespace and release identity.

        Args:
            repository: GitHub owner/repository used as the GHCR image name.
            revision: Full source commit SHA.
            version: Package release version.

        Returns:
            None: Stores the destination and bounded Docker command runner.
        """
        if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repository):
            raise ValueError("Expected a GitHub owner/repository")
        if not GIT_SHA.fullmatch(revision) or not PACKAGE_VERSION.fullmatch(version):
            raise ValueError("Invalid publication revision or version")
        self._image = f"ghcr.io/{repository.lower()}"
        self._repository = repository
        self._revision = revision
        self._version = version
        self._docker = CommandRunner("docker", timeout=REGISTRY_TIMEOUT_SECONDS)
        return None

    def _manifest(self, reference: str) -> dict[str, object] | None:
        """Inspect a remote manifest, treating only explicit absence as missing.

        Args:
            reference: Fully qualified GHCR image reference.

        Returns:
            dict[str, object] | None: Existing manifest or a registry absence response.

        Raises:
            RuntimeError: If authentication, connectivity or inspection fails.
        """
        result = self._docker.run(
            ["buildx", "imagetools", "inspect", "--raw", reference], check=False
        )
        if result.returncode == 0:
            return object_fields(json.loads(result.stdout))
        message = result.stderr.casefold()
        if any(word in message for word in ("unauthorized", "denied", "forbidden")):
            raise RuntimeError(f"Cannot inspect {reference}: {result.stderr}")
        if "manifest unknown" in message or "not found" in message:
            return None
        raise RuntimeError(f"Cannot inspect {reference}: {result.stderr}")

    @staticmethod
    def _index_identity(manifest: dict[str, object]) -> tuple[tuple[str, str, str], ...]:
        """Compare runtime platform digests, ignoring non-runtime index annotations.

        Args:
            manifest: Multi-platform registry index.

        Returns:
            tuple[tuple[str, str, str], ...]: Sorted OS, architecture and digest triples.
        """
        descriptors = manifest.get("manifests")
        if not isinstance(descriptors, list) or len(descriptors) != len(ARCHITECTURES):
            raise ValueError("Release index must contain exactly amd64 and arm64 images")
        identities: list[tuple[str, str, str]] = []
        for value in descriptors:
            descriptor = object_fields(value)
            platform = object_fields(descriptor.get("platform"))
            architecture, digest = platform.get("architecture"), descriptor.get("digest")
            if (
                not isinstance(architecture, str)
                or platform.get("os") != "linux"
                or architecture not in ARCHITECTURES
            ):
                raise ValueError("Unexpected release index platform")
            if not isinstance(digest, str) or not IMAGE_DIGEST.fullmatch(digest):
                raise ValueError("Invalid platform descriptor")
            identities.append(("linux", architecture, digest))
        if {item[1] for item in identities} != ARCHITECTURES:
            raise ValueError("Duplicate release index architecture")
        return tuple(sorted(identities))

    def _pinned_reference(self, reference: str) -> str:
        """Resolve a registry descriptor to an immutable digest reference.

        Args:
            reference: Existing image/index reference.

        Returns:
            str: GHCR repository plus validated descriptor digest.
        """
        output = self._docker.run(
            [
                "buildx",
                "imagetools",
                "inspect",
                "--format",
                "{{json .Manifest}}",
                reference,
            ]
        ).stdout
        digest = object_fields(json.loads(output)).get("digest")
        if not isinstance(digest, str) or not IMAGE_DIGEST.fullmatch(digest):
            raise ValueError("Registry did not supply a valid manifest digest")
        return f"{self._image}@{digest}"

    def _publish_architecture(self, directory: Path) -> str:
        """Load and verify one tested image, refusing a different image under its SHA tag.

        Args:
            directory: Downloaded artifact containing image.json and image.tar.gz.

        Returns:
            str: Immutable per-architecture registry reference.
        """
        metadata = object_fields(json.loads((directory / "image.json").read_text(encoding="utf-8")))
        image, architecture = metadata.get("image_id"), metadata.get("architecture")
        if not isinstance(image, str) or not isinstance(architecture, str):
            raise ValueError("Artifact image identity is missing")
        validate_identity(image, architecture, self._revision, self._version)
        if metadata.get("revision") != self._revision or metadata.get("version") != self._version:
            raise ValueError("Artifact comes from a different revision/version")
        self._docker.run(["image", "load", "--input", str(directory / "image.tar.gz")])
        info = object_fields(json.loads(self._docker.run(["image", "inspect", image]).stdout)[0])
        labels = object_fields(object_fields(info.get("Config")).get("Labels"))
        if (
            info.get("Id") != image
            or info.get("Architecture") != architecture
            or info.get("Os") != "linux"
            or labels.get("org.opencontainers.image.revision") != self._revision
            or labels.get("org.opencontainers.image.version") != self._version
            or labels.get("org.opencontainers.image.source")
            != f"https://github.com/{self._repository}"
        ):
            raise ValueError("Loaded image differs from the tested artifact")
        reference = f"{self._image}:sha-{self._revision}-{architecture}"
        existing = self._manifest(reference)
        if existing is None:
            self._docker.run(["image", "tag", image, reference])
            self._docker.run(["image", "push", reference])
            existing = self._manifest(reference)
        if existing is None or object_fields(existing.get("config")).get("digest") != image:
            raise ValueError("Refusing to replace a commit tag with a different image")
        pinned = self._pinned_reference(reference)
        verified = self._manifest(pinned)
        if verified is None or object_fields(verified.get("config")).get("digest") != image:
            raise ValueError("Registry image changed during verification")
        return pinned

    def publish(self, artifacts: Path, candidate: str) -> None:
        """Create one tested multi-platform index and promote stable only at the end.

        Args:
            artifacts: Download root containing exactly two architecture artifact directories.
            candidate: Unique workflow-run/attempt identifier for the temporary index tag.

        Returns:
            None: Commit/version tags and stable point to the tested platform pair.
        """
        if not re.fullmatch(r"[0-9]+-[0-9]+", candidate):
            raise ValueError("Candidate must identify a workflow run and attempt")
        directories = sorted(path.parent for path in artifacts.glob("*/image.json"))
        if len(directories) != len(ARCHITECTURES):
            raise ValueError("Both architecture artifacts are required")
        architectures = [
            json.loads((path / "image.json").read_text())["architecture"] for path in directories
        ]
        if set(architectures) != ARCHITECTURES:
            raise ValueError("Artifact architectures must be unique")
        references = [self._publish_architecture(path) for path in directories]
        candidate_ref = f"{self._image}:candidate-{candidate}"
        self._docker.run(["buildx", "imagetools", "create", "--tag", candidate_ref, *references])
        manifest = self._manifest(candidate_ref)
        if manifest is None:
            raise ValueError("Published candidate index is missing")
        expected = self._index_identity(manifest)
        pinned = self._pinned_reference(candidate_ref)
        verified = self._manifest(pinned)
        if verified is None or self._index_identity(verified) != expected:
            raise ValueError("Registry index changed during verification")
        permanent = [f"{self._image}:sha-{self._revision}", f"{self._image}:v{self._version}"]
        missing: list[str] = []
        for reference in permanent:
            existing = self._manifest(reference)
            if existing is not None and self._index_identity(existing) != expected:
                raise ValueError("Refusing to overwrite an existing release version/commit")
            if existing is None:
                missing.append(reference)
        for reference in missing:
            self._docker.run(["buildx", "imagetools", "create", "--tag", reference, pinned])
        self._docker.run(
            [
                "buildx",
                "imagetools",
                "create",
                "--tag",
                f"{self._image}:stable",
                pinned,
            ]
        )
        return None
