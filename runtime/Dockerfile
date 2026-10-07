FROM mcr.microsoft.com/dotnet/aspnet:6.0.36-bullseye-slim
# The old game runtime requires Bullseye's libssl1.1. Use its archived packages;
# signed package verification remains enabled (only expired index dates are ignored).
RUN printf 'deb https://archive.debian.org/debian bullseye main\ndeb https://archive.debian.org/debian-security bullseye-security main\n' > /etc/apt/sources.list \
    && apt-get -o Acquire::Check-Valid-Until=false update && apt-get install -y --no-install-recommends \
    libgl1 libcurl4 libssl1.1 libatomic1 libglu1-mesa freeglut3 \
    libglew2.1 libglfw3 libmpg123-0 libao4 libicu67 ca-certificates \
    && rm -rf /var/lib/apt/lists/*
COPY entrypoint.sh /entrypoint.sh
RUN chmod 755 /entrypoint.sh
ENTRYPOINT ["/entrypoint.sh"]
