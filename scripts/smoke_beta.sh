#!/usr/bin/env sh
set -eu

: "${BASE_URL:?BASE_URL is required, for example https://api.staging.example.com}"
curl --fail --silent --show-error "$BASE_URL/health/live/"
curl --fail --silent --show-error "$BASE_URL/health/ready/"
curl --fail --silent --show-error "$BASE_URL/api/v1/game-definitions/" >/dev/null
printf '%s\n' "beta_smoke=passed"
