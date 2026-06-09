from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
WORKFLOW = REPO_ROOT / ".github" / "workflows" / "docker-publish.yml"
DOCKER_IMAGES_DOC = REPO_ROOT / "docs" / "deployment" / "docker-images.md"
ROOT_README = REPO_ROOT / "README.md"
DOCS_README = REPO_ROOT / "docs" / "README.md"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_docker_publish_workflow_supports_tag_and_manual_release_publish() -> None:
    content = _read(WORKFLOW)

    assert "name: publish-docker-images" in content
    assert "tags:" in content
    assert '"v*"' in content
    assert "workflow_dispatch:" in content
    assert "image_tag:" in content
    assert "packages: write" in content
    assert "docker/login-action@v3" in content
    assert "docker/build-push-action@v6" in content
    assert "github.event_name" in content
    assert "workflow_dispatch" in content
    assert "inputs.image_tag" in content
    assert "GITHUB_REF_TYPE" in content
    assert "GITHUB_REF_NAME" in content
    assert "Checkout release ref" in content


def test_docker_publish_workflow_defines_expected_ghcr_images() -> None:
    content = _read(WORKFLOW)

    assert "REGISTRY: ghcr.io" in content
    assert "IMAGE_NAMESPACE: skeinrank" in content

    expected = {
        "skeinrank-governance-api": "deploy/docker/governance-api.Dockerfile",
        "skeinrank-governance-worker": "deploy/docker/governance-api.Dockerfile",
        "skeinrank-ui": "deploy/docker/ui.Dockerfile",
    }

    for image, dockerfile in expected.items():
        assert f"image: {image}" in content
        assert f"dockerfile: {dockerfile}" in content
        assert (
            "${{ env.REGISTRY }}/${{ env.IMAGE_NAMESPACE }}/${{ matrix.image }}:${{ steps.release.outputs.tag }}"
            in content
        )

    tag_lines = [
        line.strip()
        for line in content.splitlines()
        if line.strip().startswith("${{ env.REGISTRY }}")
    ]
    assert tag_lines == [
        "${{ env.REGISTRY }}/${{ env.IMAGE_NAMESPACE }}/${{ matrix.image }}:${{ steps.release.outputs.tag }}"
    ]


def test_docker_image_docs_explain_automatic_and_manual_publish_paths() -> None:
    content = _read(DOCKER_IMAGES_DOC)

    assert "GHCR Docker image publishing" in content
    assert "ghcr.io/skeinrank/skeinrank-governance-api:<tag>" in content
    assert "ghcr.io/skeinrank/skeinrank-governance-worker:<tag>" in content
    assert "ghcr.io/skeinrank/skeinrank-ui:<tag>" in content
    assert "Automatic release publish" in content
    assert "Manual publish for an existing tag" in content
    assert "v0.10.0-beta.1" in content
    assert (
        "latest is not published for beta releases" in content
        or "`latest` is not published for beta releases" in content
    )
    assert "deploy/docker/governance-api.Dockerfile" in content
    assert "deploy/docker/ui.Dockerfile" in content


def test_readme_and_docs_index_link_docker_images_docs() -> None:
    readme = _read(ROOT_README)
    docker_images_doc = _read(DOCKER_IMAGES_DOC)
    docs_readme = _read(DOCS_README)

    assert "deployment/docker-images.md" in docs_readme
    assert ".github/workflows/docker-publish.yml" in readme
    assert "v0.10.0-beta.1" in docker_images_doc
