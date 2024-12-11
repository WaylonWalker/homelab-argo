FROM ubuntu:noble
ENV PATH="/root/.local/bin:${PATH}"
RUN apt-get update && apt-get install -y curl
RUN curl -LsSf https://astral.sh/uv/install.sh | sh
RUN uv python install 3.13
