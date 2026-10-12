# syntax=docker/dockerfile:1
FROM ubuntu:24.04 AS build
ARG DEBIAN_FRONTEND=noninteractive
ARG JOBS=4
ENV OPAMROOT=/opt/opam JOBS=${JOBS} OPAMJOBS=${JOBS}
RUN apt-get update && apt-get install -y --no-install-recommends \
    git curl ca-certificates python3 python3-venv python3-setuptools opam sudo patch \
    libgmp-dev libmpfr-dev m4 pkg-config build-essential unzip rsync \
    bison flex && rm -rf /var/lib/apt/lists/*
WORKDIR /opt/verena
COPY artifact/build.sh artifact/requirements.txt artifact/skeleton_qe.py artifact/verify_native_moves.py artifact/
COPY artifact/patches/skeleton-interface.patch artifact/patches/
RUN bash artifact/build.sh
COPY . .
RUN artifact/.venv/bin/python -m pip install -r artifact/requirements-plots.txt && \
    artifact/.venv/bin/python artifact/prepare_figure3.py && \
    bash artifact/install_dependencies.sh --check

FROM ubuntu:24.04 AS runtime
ARG DEBIAN_FRONTEND=noninteractive
ARG SOURCE_REVISION=unknown
LABEL org.opencontainers.image.source="https://github.com/tonyPan123/Verena-AE" \
      org.opencontainers.image.revision="${SOURCE_REVISION}"
ENV VERENA_SOURCE_REVISION=${SOURCE_REVISION} PYTHONUNBUFFERED=1
RUN apt-get update && apt-get install -y --no-install-recommends \
    python3 git ca-certificates libgmp10 libmpfr6 libgomp1 libstdc++6 && \
    rm -rf /var/lib/apt/lists/*
WORKDIR /opt/verena
COPY . .
COPY --from=build /opt/verena/artifact/.venv artifact/.venv
COPY --from=build /opt/verena/artifact/bin artifact/bin
COPY --from=build /opt/verena/artifact/_build/versions.txt artifact/_build/versions.txt
COPY --from=build /opt/verena/artifact/_build/strategy-improvement/simsat.native artifact/_build/strategy-improvement/simsat.native
COPY --from=build /opt/opam/simsat/lib /opt/opam/simsat/lib
COPY --from=build /opt/opam/simsat/share/apron /opt/opam/simsat/share/apron
RUN mkdir -p /results && \
    bash artifact/install_dependencies.sh --check
ENTRYPOINT ["/bin/bash", "/opt/verena/artifact/docker-entrypoint.sh"]
CMD ["help"]
