# Shared by every location that forwards to the API.
# $http_host keeps the port, so the API's same-origin check sees the browser's real Host.
proxy_set_header Host $http_host;
# Overwrite (never append to) the forwarded address so clients cannot spoof it.
proxy_set_header X-Forwarded-For $remote_addr;
proxy_set_header X-Forwarded-Proto $scheme;
proxy_connect_timeout 5s;
