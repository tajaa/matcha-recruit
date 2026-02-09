#!/bin/sh
set -e

if [ -n "$API_URL" ]; then
    echo "Injecting API_URL: $API_URL"
    find /usr/share/nginx/html -type f -name "*.js" -exec sed -i "s|http://localhost:8004|$API_URL|g" {} \;
fi

if [ -n "$WS_URL" ]; then
    echo "Injecting WS_URL: $WS_URL"
    find /usr/share/nginx/html -type f -name "*.js" -exec sed -i "s|ws://localhost:8004|$WS_URL|g" {} \;
fi

exec "$@"
