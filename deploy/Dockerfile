# agentic-backoffice container image.
#
# Build from the repo root:
#   docker build -f deploy/Dockerfile -t agentic-backoffice .
#
# The image contains the Python package only. Agent definitions, skills, company files and
# state are NOT baked in: mount the repo checkout at /opt/backoffice. The Claude Agent SDK
# wheel bundles the Claude Code CLI, so no separate Node.js or `claude` install is needed.
#
# The container runs one `backoffice tick` and exits. Call it from the host every 5 minutes
# (systemd timer or cron), for example:
#
#   docker run --rm \
#     --read-only \
#     --cap-drop ALL --security-opt no-new-privileges \
#     --tmpfs /tmp --tmpfs /home/backoffice \
#     -v /opt/backoffice:/opt/backoffice \
#     --env-file /etc/backoffice.env \
#     agentic-backoffice
#
# Hardening notes:
# - Root filesystem read-only (--read-only). Writable: the mounted repo (workspace/ and
#   .backoffice/ are written to), plus tmpfs for /tmp and the home directory.
# - Mount only the repo checkout. If you want the source read-only, mount it read-only and
#   add two writable volumes on top: -v /opt/backoffice:/opt/backoffice:ro with
#   -v /var/lib/backoffice/workspace:/opt/backoffice/workspace and
#   -v /var/lib/backoffice/state:/opt/backoffice/.backoffice (create both first, owned by
#   uid 10001). `.backoffice/` must persist between runs: it holds the ledger.
# - No secrets in the image or in the build context. Pass them at run time (--env-file or
#   orchestrator secrets). Do not COPY .env into the image.
# - Non-root user (uid 10001). Do not run with --privileged or mount the Docker socket.
# - Pin the base image by digest in production and rebuild when the Agent SDK is bumped
#   (pyproject.toml pins the SDK version; run `make eval` before bumping).
# - The tmpfs home means the Claude CLI's own session files vanish after each run. That is
#   intended: resumption within a run does not need them to outlive the container.

FROM python:3.12-slim

# git is required by the site.pull_request handler. Install `gh` as well only if you set
# `push: true` for that action.
RUN apt-get update \
    && apt-get install -y --no-install-recommends git ca-certificates \
    && rm -rf /var/lib/apt/lists/*

RUN useradd --system --uid 10001 --create-home --home-dir /home/backoffice --shell /usr/sbin/nologin backoffice

WORKDIR /src
COPY pyproject.toml README.md ./
COPY src ./src
RUN pip install --no-cache-dir .

ENV BACKOFFICE_ROOT=/opt/backoffice \
    HOME=/home/backoffice \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

WORKDIR /opt/backoffice
USER backoffice

CMD ["backoffice", "tick"]
