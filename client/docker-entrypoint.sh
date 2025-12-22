#!/bin/sh
set -e

# Replace environment variables in built JavaScript files
# This allows runtime configuration of API URLs

if [ -n "$API_URL" ]; then
    echo "Injecting API_URL: $API_URL"
    # Replace HTTP API URL
    find /usr/share/nginx/html -type f -name "*.js" -exec sed -i "s|http://localhost:8000|$API_URL|g" {} \;
fi

if [ -n "$WS_URL" ]; then
    echo "Injecting WS_URL: $WS_URL"
    # Replace WebSocket URL
    find /usr/share/nginx/html -type f -name "*.js" -exec sed -i "s|ws://localhost:8000|$WS_URL|g" {} \;
fi

# Execute the CMD
exec "$@"
