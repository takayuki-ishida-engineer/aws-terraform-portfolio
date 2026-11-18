# Temporary local image for the Step 2 rehearsal; built and removed in the same job, never pushed.
# Same digest-pinned Ubuntu as scripts/emulator-verification (versions.json ubuntu_image).
FROM ubuntu:24.04@sha256:77eb101c607d6e3d4f5ad0c8a02c2136c689b98aba1f359e6502ba517e5c57ec
RUN apt-get update && apt-get install -y --no-install-recommends python3 ca-certificates iproute2 unzip && rm -rf /var/lib/apt/lists/*
COPY . /opt/step2-context
RUN set -eu; c=/opt/step2-context; t=/opt/step2-tools; \
    cd "$c" && sha256sum --check --quiet context.sha256; \
    mkdir -p "$t/bin" "$t/harness"; \
    cp -a "$c/emulator" "$t/emulator"; ln -s "$t/emulator/opt/aws-emulator/bin/aws-emulator" "$t/bin/aws-emulator"; \
    unzip -q "$c/awscli.zip" -d /tmp/awscli; /tmp/awscli/aws/install --install-dir "$t/aws-cli" --bin-dir "$t/bin" >/dev/null; rm -rf /tmp/awscli; \
    install -m 0755 "$c/terraform" "$t/bin/terraform"; \
    cp -a "$c/mirror" "$t/mirror"; cp -a "$c/source" "$t/source"; cp "$c"/harness/*.py "$t/harness/"; \
    cp "$c/prepared.json" "$c/run.json" "$t/"; rm -rf "$c"; \
    chmod -R a+rX,go-w "$t"; mkdir -p /opt/step2-work /opt/step2-evidence
USER 1000:1000
ENV HOME=/opt/step2-work/home PYTHONDONTWRITEBYTECODE=1 EMULATOR_TELEMETRY=off
ENTRYPOINT ["python3", "-I", "/opt/step2-tools/harness/rehearse.py"]
