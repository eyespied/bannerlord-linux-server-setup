#!/bin/sh
set -eu
cd /game/bin/Linux64_Shipping_Server
export LD_LIBRARY_PATH="$PWD${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
test -s /run/secrets/token || { echo 'Missing private server token' >&2; exit 1; }
token=$(cat /run/secrets/token)
test -n "$token" || exit 1
exec dotnet TaleWorlds.Starter.DotNetCore.Linux.dll "$MODULES" \
    /dedicatedcustomserverconfigfile ../../Modules/Native/server-config.txt \
    /tickrate "$TICKRATE" /dedicatedcustomserverauthtoken "$token" \
    /dedicatedcustomserver "$PORT" USER 0 /playerhosteddedicatedserver
