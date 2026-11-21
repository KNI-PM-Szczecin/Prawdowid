# Build context: eval/. Runs the test harness against a running backend (see docs/docker.md).
FROM python:3.12-slim
COPY --from=ghcr.io/astral-sh/uv:0.13.7 /uv /bin/uv
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PROJECT_ENVIRONMENT=/opt/venv PATH="/opt/venv/bin:$PATH"
WORKDIR /srv
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev
COPY cases.json ./cases.json
COPY prawdowid_eval ./prawdowid_eval
ENTRYPOINT ["python", "-m", "prawdowid_eval"]
CMD ["run", "--url", "http://backend:3001", "--cases", "/srv/cases.json", "--out", "/srv/reports"]
