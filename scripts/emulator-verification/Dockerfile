FROM ubuntu:24.04@sha256:77eb101c607d6e3d4f5ad0c8a02c2136c689b98aba1f359e6502ba517e5c57ec
RUN apt-get update && apt-get install -y --no-install-recommends python3 ca-certificates iproute2 unzip && rm -rf /var/lib/apt/lists/*
COPY artifacts /opt/artifacts
RUN cd /opt/artifacts && sha256sum --check artifacts.sha256 && apt-get update && apt-get install -y --no-install-recommends ./emulator.deb && unzip -q awscli.zip && ./aws/install --install-dir /opt/aws-cli --bin-dir /usr/local/bin && unzip -q terraform.zip terraform -d /usr/local/bin && rm -rf /var/lib/apt/lists/* /opt/artifacts/aws /opt/artifacts/*.zip /opt/artifacts/*.deb
COPY verification /opt/verification
RUN mkdir /work && chmod 755 /work
USER 1000:1000
ENV HOME=/work/home PYTHONDONTWRITEBYTECODE=1 EMULATOR_TELEMETRY=off
ENTRYPOINT ["python3", "/opt/verification/lifecycle.py"]
