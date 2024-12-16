FROM ubuntu:noble
ENV PATH="/root/.local/bin:${PATH}"
RUN apt-get update && apt-get install -y curl git
RUN curl -LsSf https://astral.sh/uv/install.sh | sh
RUN uv python install 3.13
RUN uv pip install hatch --system
RUN curl https://i.wayl.one/casey/just | bash && mv just /usr/local/bin
