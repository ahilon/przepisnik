"""Validate archive identity and immutable promotion against a simulated registry."""

import hashlib
import json
import subprocess
from collections.abc import Sequence
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from scripts.image_registry import ImagePublisher, archive_image, object_fields, validate_identity

REVISION = "a" * 40
VERSION = "1.11.1"
REPOSITORY = "ahilon/przepisnik"
IMAGE_IDS = {"amd64": "sha256:" + "1" * 64, "arm64": "sha256:" + "2" * 64}


def image_info(architecture: str) -> dict[str, object]:
    """Describe one tested Docker image.

    Args:
        architecture: The platform under test.

    Returns:
        dict[str, object]: Minimal image inspection with expected source labels.
    """
    labels = {
        "org.opencontainers.image.revision": REVISION,
        "org.opencontainers.image.version": VERSION,
        "org.opencontainers.image.source": f"https://github.com/{REPOSITORY}",
    }
    return {
        "Id": IMAGE_IDS[architecture],
        "Os": "linux",
        "Architecture": architecture,
        "Config": {"Labels": labels},
    }


class Registry:
    """Model config IDs and platform indexes without running Docker or using a token."""

    def __init__(self) -> None:
        """Initialize an empty registry and the expected local images.

        Returns:
            None: Creates state and a complete command audit.
        """
        self.calls: list[list[str]] = []
        self.images = {IMAGE_IDS[arch]: image_info(arch) for arch in IMAGE_IDS}
        self.manifests: dict[str, dict[str, object]] = {}
        self.tags: dict[str, str] = {}
        return None

    def run(
        self, arguments: Sequence[str], *, check: bool = True
    ) -> subprocess.CompletedProcess[str]:
        """Execute the registry subset required for publication.

        Args:
            arguments: Explicit Docker argument vector.
            check: Normal runner error policy, unused because failures are returned for inspect.

        Returns:
            subprocess.CompletedProcess[str]: Deterministic Docker response.
        """
        del check
        args = list(arguments)
        self.calls.append(args)
        output = ""
        if args[:2] == ["image", "inspect"]:
            output = json.dumps([self.images[args[2]]])
        elif args[:2] == ["image", "save"]:
            Path(args[3]).write_bytes(b"synthetic image archive")
        elif args[:2] == ["image", "tag"]:
            self.tags[args[3]] = args[2]
        elif args[:2] == ["image", "push"]:
            self.manifests[args[2]] = {"config": {"digest": self.tags[args[2]]}}
        elif args[:3] == ["buildx", "imagetools", "inspect"]:
            if args[-1] not in self.manifests:
                return subprocess.CompletedProcess(args, 1, "", "manifest unknown")
            manifest = self.manifests[args[-1]]
            if "--format" in args:
                encoded = json.dumps(manifest, sort_keys=True).encode()
                digest = "sha256:" + hashlib.sha256(encoded).hexdigest()
                self.manifests[f"ghcr.io/{REPOSITORY}@{digest}"] = manifest
                output = json.dumps({"digest": digest})
            else:
                output = json.dumps(manifest)
        elif args[:3] == ["buildx", "imagetools", "create"]:
            tag, sources = args[4], args[5:]
            if len(sources) == 1:
                self.manifests[tag] = self.manifests[sources[0]]
            else:
                descriptors = []
                for source in sources:
                    config = object_fields(self.manifests[source]["config"])
                    architecture = next(
                        arch for arch, image in IMAGE_IDS.items() if image == config["digest"]
                    )
                    descriptors.append(
                        {
                            "platform": {"os": "linux", "architecture": architecture},
                            "digest": source.split("@", 1)[1],
                        }
                    )
                self.manifests[tag] = {"manifests": descriptors}
        return subprocess.CompletedProcess(args, 0, output, "")


@pytest.fixture
def registry(monkeypatch: pytest.MonkeyPatch) -> Registry:
    """Bind publication to an in-memory registry.

    Args:
        monkeypatch: Scoped command-runner replacement.

    Returns:
        Registry: Auditable simulated registry.
    """
    fake = Registry()
    monkeypatch.setattr("scripts.image_registry.CommandRunner", MagicMock(return_value=fake))
    return fake


def artifacts(root: Path) -> Path:
    """Write two architecture metadata files without user data.

    Args:
        root: Disposable artifact root.

    Returns:
        Path: Root holding the expected architecture pair.
    """
    for architecture, image in IMAGE_IDS.items():
        folder = root / architecture
        folder.mkdir(parents=True)
        metadata = {
            "image_id": image,
            "architecture": architecture,
            "revision": REVISION,
            "version": VERSION,
        }
        (folder / "image.json").write_text(json.dumps(metadata), encoding="utf-8")
        (folder / "image.tar.gz").write_bytes(b"archive loaded by fake Docker")
    return root


def test_only_tested_images_are_promoted_and_retry_is_idempotent(
    registry: Registry, tmp_path: Path
) -> None:
    """Promote the verified pair without any build command and retain exact version identity.

    Args:
        registry: In-memory image state and command audit.
        tmp_path: Disposable artifacts.

    Returns:
        None: Stable is created last, and replaying the same images preserves it.
    """
    source = artifacts(tmp_path / "artifacts")
    publisher = ImagePublisher(REPOSITORY, REVISION, VERSION)
    publisher.publish(source, "123-1")
    assert registry.calls[-1][4] == f"ghcr.io/{REPOSITORY}:stable"
    assert all("build" not in command for command in registry.calls)
    stable = registry.manifests[f"ghcr.io/{REPOSITORY}:stable"]
    publisher.publish(source, "123-2")
    assert registry.manifests[f"ghcr.io/{REPOSITORY}:stable"] == stable


def test_existing_different_image_blocks_stable(registry: Registry, tmp_path: Path) -> None:
    """Refuse mutation when a SHA tag already identifies a different tested image.

    Args:
        registry: In-memory image state and command audit.
        tmp_path: Disposable artifacts.

    Returns:
        None: No stable promotion or overwrite occurs.
    """
    reference = f"ghcr.io/{REPOSITORY}:sha-{REVISION}-amd64"
    registry.manifests[reference] = {"config": {"digest": "sha256:" + "f" * 64}}
    with pytest.raises(ValueError, match="commit tag"):
        ImagePublisher(REPOSITORY, REVISION, VERSION).publish(
            artifacts(tmp_path / "artifacts"), "123-1"
        )
    assert f"ghcr.io/{REPOSITORY}:stable" not in registry.manifests
    assert not any(command[:2] == ["image", "push"] for command in registry.calls)


def test_existing_version_cannot_change_platform_digests(
    registry: Registry, tmp_path: Path
) -> None:
    """Reject an already published package version without moving the previous stable.

    Args:
        registry: In-memory image state and command audit.
        tmp_path: Disposable artifacts.

    Returns:
        None: Permanent version identity and stable remain intact.
    """
    publisher = ImagePublisher(REPOSITORY, REVISION, VERSION)
    registry.manifests[f"ghcr.io/{REPOSITORY}:v{VERSION}"] = {
        "manifests": [
            {"platform": {"os": "linux", "architecture": arch}, "digest": "sha256:" + "e" * 64}
            for arch in IMAGE_IDS
        ]
    }
    with pytest.raises(ValueError, match="existing release"):
        publisher.publish(artifacts(tmp_path / "artifacts"), "123-1")
    assert f"ghcr.io/{REPOSITORY}:stable" not in registry.manifests


@pytest.mark.parametrize("error", ["unauthorized", "denied: not found", "connection timed out"])
def test_registry_failures_do_not_mean_an_absent_image(
    registry: Registry, monkeypatch: pytest.MonkeyPatch, tmp_path: Path, error: str
) -> None:
    """Fail closed on authentication/network errors instead of overwriting an existing tag.

    Args:
        registry: Simulated Docker commands.
        monkeypatch: Scoped registry inspection failure.
        tmp_path: Disposable artifact root.
        error: Registry diagnostic to reject.

    Returns:
        None: Publication fails before an image push.
    """
    original = registry.run

    def failing_inspect(
        arguments: Sequence[str], *, check: bool = True
    ) -> subprocess.CompletedProcess[str]:
        """Return a registry failure while preserving other fake Docker behavior.

        Args:
            arguments: Docker arguments.
            check: Caller error policy.

        Returns:
            subprocess.CompletedProcess[str]: Inspection error or normal result.
        """
        if list(arguments[:3]) == ["buildx", "imagetools", "inspect"]:
            return subprocess.CompletedProcess(arguments, 1, "", error)
        return original(arguments, check=check)

    monkeypatch.setattr(registry, "run", failing_inspect)
    with pytest.raises(RuntimeError, match="Cannot inspect"):
        ImagePublisher(REPOSITORY, REVISION, VERSION).publish(
            artifacts(tmp_path / "artifacts"), "123-1"
        )
    assert not any(command[:2] == ["image", "push"] for command in registry.calls)


def test_artifacts_must_match_revision_and_architecture(registry: Registry, tmp_path: Path) -> None:
    """Reject missing platforms, wrong provenance and unexpected image labels.

    Args:
        registry: Simulated registry and local image state.
        tmp_path: Disposable artifacts.

    Returns:
        None: Incorrect artifacts cannot reach stable.
    """
    publisher = ImagePublisher(REPOSITORY, REVISION, VERSION)
    with pytest.raises(ValueError, match="Both architecture"):
        publisher.publish(tmp_path, "123-1")
    source = artifacts(tmp_path / "artifacts")
    file = source / "amd64/image.json"
    metadata = json.loads(file.read_text())
    metadata["revision"] = "b" * 40
    file.write_text(json.dumps(metadata))
    with pytest.raises(ValueError, match="different revision"):
        publisher.publish(source, "123-1")
    metadata["revision"] = REVISION
    file.write_text(json.dumps(metadata))
    registry.images[IMAGE_IDS["amd64"]]["Architecture"] = "arm64"
    with pytest.raises(ValueError, match="differs"):
        publisher.publish(source, "123-1")
    assert f"ghcr.io/{REPOSITORY}:stable" not in registry.manifests


def test_archive_contains_exact_verified_image(registry: Registry, tmp_path: Path) -> None:
    """Export a verified config ID and refuse a mismatched platform.

    Args:
        registry: Simulated image exporter.
        tmp_path: Temporary destination.

    Returns:
        None: Archive metadata retains source identity and no build was performed.
    """
    destination = tmp_path / "archive"
    archive_image(IMAGE_IDS["amd64"], "amd64", REVISION, VERSION, destination)
    assert (destination / "image.tar.gz").is_file()
    assert registry.calls[-1][:2] == ["image", "save"]
    assert not (destination / "image.tar").exists()
    assert json.loads((destination / "image.json").read_text())["image_id"] == IMAGE_IDS["amd64"]
    with pytest.raises(ValueError, match="identity"):
        archive_image(IMAGE_IDS["amd64"], "arm64", REVISION, VERSION, tmp_path / "wrong")


@pytest.mark.parametrize(
    "image,architecture,revision,version",
    [
        ("mutable:tag", "amd64", REVISION, VERSION),
        (IMAGE_IDS["amd64"], "unknown", REVISION, VERSION),
        (IMAGE_IDS["amd64"], "amd64", "--unsafe", VERSION),
        (IMAGE_IDS["amd64"], "amd64", REVISION, "bad\noutput=1"),
    ],
)
def test_untrusted_image_identity_is_rejected(
    image: str, architecture: str, revision: str, version: str
) -> None:
    """Validate every value before invoking a Docker command.

    Args:
        image: Candidate image identity.
        architecture: Candidate architecture.
        revision: Candidate commit.
        version: Candidate package version.

    Returns:
        None: Invalid identity fields are rejected.
    """
    with pytest.raises(ValueError):
        validate_identity(image, architecture, revision, version)
    with pytest.raises(ValueError):
        object_fields([])
