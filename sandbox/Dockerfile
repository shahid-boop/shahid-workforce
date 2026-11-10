# Restricted execution image for agent-generated code.
#
# Runtime hardening is applied by sandbox.policy.ExecutionPolicy when the
# container is launched (docker run flags): no network, read-only root
# filesystem, non-root UID, --cap-drop ALL, memory/CPU/PID limits and a
# wall-clock timeout. This file only prepares the immutable base layer.
FROM python:3.12-slim

# No package installs: the image must stay minimal and reproducible.
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

# Work directory for mounted task files; runtime mounts it read-write
# while the root filesystem stays read-only.
RUN mkdir -p /work && chown 65534:65534 /work

# Drop to nobody immediately; docker run also passes --user 65534:65534.
USER 65534:65534
WORKDIR /work

# The runner supplies the program via `python -c`; no default CMD keeps
# accidental `docker run image` invocations from doing anything.
CMD ["python", "-c", "raise SystemExit('no program supplied')"]
