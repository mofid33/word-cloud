FROM python:3.12.8-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DEFAULT_TIMEOUT=120 \
    PIP_ROOT_USER_ACTION=ignore \
    MPLCONFIGDIR=/tmp/matplotlib \
    HF_HOME=/var/lib/word-cloud/models

ARG TORCH_INDEX_URL=https://download.pytorch.org/whl/cpu
ARG TORCH_SPEC="torch>=2.2,<3.0"

WORKDIR /app

RUN groupadd --system --gid 10001 wordcloud \
    && useradd --system --uid 10001 --gid wordcloud --home-dir /nonexistent --shell /usr/sbin/nologin wordcloud \
    && mkdir -p /var/lib/word-cloud/models /tmp/matplotlib \
    && chown -R wordcloud:wordcloud /var/lib/word-cloud /tmp/matplotlib

COPY requirements.txt /app/requirements.txt
RUN python -m pip install --upgrade "pip==25.2" \
    && python -m pip install --retries 10 --resume-retries 20 --index-url "${TORCH_INDEX_URL}" "${TORCH_SPEC}" \
    && python -m pip install --retries 10 --resume-retries 20 --requirement /app/requirements.txt \
    && mkdir -p /opt/word-cloud \
    && python -m pip freeze --all | sort > /opt/word-cloud/resolved-dependencies.txt

COPY src /app/src

USER 10001:10001

EXPOSE 5000

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:5000/api/v1/health/live', timeout=3).read()" || exit 1

CMD ["python", "-m", "uvicorn", "src.host.app:app", "--host", "0.0.0.0", "--port", "5000", "--proxy-headers", "--no-server-header"]
