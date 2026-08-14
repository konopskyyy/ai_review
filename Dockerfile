FROM python:3.12-slim-bookworm

ARG OPENCODE_VERSION=1.18.18

ENV DEBIAN_FRONTEND=noninteractive \
    PATH="/root/.opencode/bin:${PATH}" \
    HOME=/root \
    OPENCODE_DISABLE_AUTOUPDATE=1 \
    OPENCODE_DISABLE_CLAUDE_CODE=1 \
    OPENCODE_DISABLE_SHARE=1

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        curl \
        git \
        ca-certificates \
    && rm -rf /var/lib/apt/lists/* \
    && curl -fsSL https://opencode.ai/install -o /tmp/opencode-install.sh \
    && bash /tmp/opencode-install.sh --version "${OPENCODE_VERSION}" --no-modify-path \
    && rm -f /tmp/opencode-install.sh \
    && opencode --version

COPY opencode/ /root/.config/opencode/
COPY skills/ /root/.config/opencode/skills/
COPY review.py /opt/ai-review/review.py
COPY entrypoint.sh /opt/ai-review/entrypoint.sh

RUN chmod +x /opt/ai-review/entrypoint.sh /opt/ai-review/review.py \
    && mkdir -p /work

WORKDIR /work
ENTRYPOINT ["/opt/ai-review/entrypoint.sh"]
