SIM ?= iPhone 17 Pro

.PHONY: generate open build test clean run run-prod release release-dry deps

generate:
	@which xcodegen > /dev/null || (echo "Installing XcodeGen..." && brew install xcodegen)
	xcodegen generate

open: generate
	open Gummfit.xcodeproj

build: generate
	xcodebuild build \
		-scheme Gummfit \
		-destination 'platform=iOS Simulator,name=$(SIM)' \
		-configuration Debug

test: generate
	xcodebuild test \
		-scheme Gummfit \
		-destination 'platform=iOS Simulator,name=$(SIM)' \
		-configuration Debug

clean:
	xcodebuild clean -scheme Gummfit
	rm -rf build/
	rm -rf DerivedData/

deps:
	brew install xcodegen

# Build + install + launch on the simulator. See run.sh for the
# error-surfacing build log + boot/install/launch details.
run:
	SIM="$(SIM)" ./run.sh

# Same as run, but points the simulator app at the production API
# (https://gummfit.com/api/cappe) instead of the local dev backend.
run-prod:
	SIM="$(SIM)" ./run-prod.sh

# Bump build number, archive, and upload to App Store Connect / TestFlight.
# Requires APPLE_API_KEY_ID / APPLE_API_ISSUER_ID / APPLE_API_KEY_PATH — see
# release-appstore.sh's header for one-time setup.
release:
	./release-appstore.sh

# Archive only, no upload — use to sanity-check signing/build before
# spending an ASC upload slot.
release-dry:
	./release-appstore.sh --no-upload
