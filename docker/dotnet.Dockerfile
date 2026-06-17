# Sandbox image for the dotnet-10-sdk environment. `dotnet test`/`dotnet restore` are built into the
# base; SAST is the generic Semgrep image. Writable HOME + NuGet/CLI caches for the non-root --user run.
FROM mcr.microsoft.com/dotnet/sdk:10.0-alpine

# Corporate root CA (see go.Dockerfile): trust it BEFORE the NuGet prewarm restore below so it works
# behind a TLS-intercepting proxy. Safe no-op when no cert is staged (dir present via certs/.gitkeep).
COPY certs/ /usr/local/share/ca-certificates/
RUN command -v update-ca-certificates >/dev/null && update-ca-certificates || true

ENV HOME=/tmp \
    DOTNET_CLI_HOME=/tmp \
    NUGET_PACKAGES=/tmp/nuget \
    XDG_DATA_HOME=/tmp/.local \
    DOTNET_NOLOGO=1 \
    DOTNET_CLI_TELEMETRY_OPTOUT=1

# --- NuGet cache prewarm (build-time, online) --------------------------------------------------
# The runtime mounts /tmp as a FRESH tmpfs (see docker_adapter --tmpfs /tmp), so anything baked into
# /tmp/nuget is masked at run time. We therefore warm the packages tickets commonly pin into a
# READ-ONLY fallback folder OUTSIDE /tmp (/opt/nuget-fallback). A machine-wide /NuGet.Config — found
# when `dotnet restore` walks /workspace → / — keeps the writable global folder on the tmpfs
# (/tmp/nuget) and adds the baked dir as a read-only fallback. Effect: these packages resolve OFFLINE
# (no network, immune to the proxy/antivirus dropping bursts of TLS connects — the NU1301 deadlock),
# while a novel/unlisted package still restores over the network into /tmp/nuget. Build runs through
# the WSL daemon trust store, so this online restore succeeds at image-build time.
RUN mkdir -p /opt/nuget-fallback /warm \
 && printf '%s\n' \
      '<Project Sdk="Microsoft.NET.Sdk">' \
      '  <PropertyGroup><TargetFramework>net10.0</TargetFramework><OutputType>Exe</OutputType></PropertyGroup>' \
      '  <ItemGroup>' \
      '    <PackageReference Include="System.CommandLine" Version="2.0.0-beta4.24528.1" />' \
      '    <PackageReference Include="Microsoft.NET.Test.Sdk" Version="17.12.0" />' \
      '    <PackageReference Include="xunit" Version="2.9.3" />' \
      '    <PackageReference Include="xunit.runner.visualstudio" Version="2.8.2" />' \
      '  </ItemGroup>' \
      '</Project>' > /warm/warm.csproj \
 && NUGET_PACKAGES=/opt/nuget-fallback dotnet restore /warm/warm.csproj \
 && chmod -R a+rX /opt/nuget-fallback \
 && rm -rf /warm /tmp/nuget /tmp/.local

# Machine-wide NuGet config: writable global folder on the runtime tmpfs + the baked read-only
# fallback. Placed at filesystem root so the restore's directory walk (/workspace → /) discovers it.
RUN printf '%s\n' \
      '<?xml version="1.0" encoding="utf-8"?>' \
      '<configuration>' \
      '  <config>' \
      '    <add key="globalPackagesFolder" value="/tmp/nuget" />' \
      '  </config>' \
      '  <fallbackPackageFolders>' \
      '    <add key="warm" value="/opt/nuget-fallback" />' \
      '  </fallbackPackageFolders>' \
      '</configuration>' > /NuGet.Config
