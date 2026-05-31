# GHCR Docker image publishing

SkeinRank publishes release Docker images to GitHub Container Registry (GHCR).
The Docker publishing workflow is intentionally release-oriented: it runs for
version tags and can also be launched manually for an existing tag.

## Images

The public image names are:

| Image | Purpose | Dockerfile |
| --- | --- | --- |
| `ghcr.io/skeinrank/skeinrank-governance-api:<tag>` | Governance API, migrations, and CLI runtime | `deploy/docker/governance-api.Dockerfile` |
| `ghcr.io/skeinrank/skeinrank-governance-worker:<tag>` | Background worker runtime; Compose/Kubernetes overrides the command | `deploy/docker/governance-api.Dockerfile` |
| `ghcr.io/skeinrank/skeinrank-ui:<tag>` | React governance console | `deploy/docker/ui.Dockerfile` |

The API and worker images are built from the same runtime Dockerfile because the
worker uses the same Python package and entry points. The worker service should
override the container command with `skeinrank-governance-worker`.

## Automatic release publish

Pushing a version tag publishes all release images with the same Docker tag:

```bash
git tag -a v0.10.0-beta.1 -m "SkeinRank v0.10.0-beta.1"
git push origin v0.10.0-beta.1
```

The workflow publishes:

```text
ghcr.io/skeinrank/skeinrank-governance-api:v0.10.0-beta.1
ghcr.io/skeinrank/skeinrank-governance-worker:v0.10.0-beta.1
ghcr.io/skeinrank/skeinrank-ui:v0.10.0-beta.1
```

`latest` is not published for beta releases. Use the explicit version tag in
Compose, Kubernetes, or Helm values.

## Manual publish for an existing tag

Use this when the git tag already exists or a previous image publish failed:

1. Open **Actions** in GitHub.
2. Select **publish-docker-images**.
3. Click **Run workflow**.
4. Set `image_tag` to an existing tag, for example `v0.10.0-beta.1`.
5. Run the workflow.

The workflow checks out that tag and publishes the images with the same tag. This
keeps the image tag tied to a reproducible repository state.

## Local sanity checks before publishing

Before pushing the tag, run the normal CI checks locally where possible:

```bash
cd packages/skeinrank-governance-api
poetry run pytest -q
cd ../..
```

You can also build the release Dockerfiles locally:

```bash
docker build -f deploy/docker/governance-api.Dockerfile -t skeinrank-governance-api:local .
docker build -f deploy/docker/ui.Dockerfile -t skeinrank-ui:local .
```


## Running the release stack

After images are published, the default Compose entrypoint pulls them automatically:

```bash
cp .env.example .env
docker compose up -d
```

Set `SKEINRANK_IMAGE_TAG` in `.env` to select the release tag. See
[`release-compose.md`](release-compose.md) for the complete public beta runbook.

## Pulling images manually

Most users should not need to run `docker pull` directly. Release Compose and
Helm values should reference the images and Docker will pull them automatically.
Manual pulls are useful for debugging:

```bash
docker pull ghcr.io/skeinrank/skeinrank-governance-api:v0.10.0-beta.1
docker pull ghcr.io/skeinrank/skeinrank-governance-worker:v0.10.0-beta.1
docker pull ghcr.io/skeinrank/skeinrank-ui:v0.10.0-beta.1
```

## Permissions

The workflow uses the repository `GITHUB_TOKEN` with `packages: write` permission.
If GHCR packages are not visible after the first run, check the repository package
visibility settings and link the package to the repository.
