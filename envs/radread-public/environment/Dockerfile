# environment/Dockerfile
FROM ubuntu:24.04
ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update && apt-get install -y \
    python3 \
    python3-pip \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /root

RUN pip3 install --break-system-packages \
    pytest==8.3.4

# Build context: environment/, after authorized images are prepared locally.
# Copy only model-visible assets. Never bake or mount verifier/gold/oracle artifacts
# into the agent image. The verifier and external key belong to a separate trusted
# phase after the agent has finished, not to this Docker build.
COPY tasks.jsonl /root/tasks.jsonl
COPY images /root/images
COPY skills /root/skills
