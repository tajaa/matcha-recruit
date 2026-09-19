# Cappe Storefront iOS

The `Ahnimal` target is the first white-label Cappe storefront app. Tenant and
API values live in `project.yml`; a new storefront can be added as another
target using the same `Sources` and `Resources` with its own bundle ID, URL
scheme, display name, tagline, and plist keys (`CappeDisplayName` and
`CappeTagline` provide the in-app branding).

```sh
make build
CAPPE_API_URL=http://127.0.0.1:8001/api/cappe make run
make test
```

`CAPPE_API_URL` is read only by Debug builds. Release builds always use the
`CappeAPIBase` value generated into the target Info.plist.
