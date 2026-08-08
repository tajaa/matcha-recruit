SIM ?= iPhone 17 Pro

.PHONY: generate open build test clean run run-prod deps

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

# `release`/`release-dry` (archive + TestFlight upload) land in Phase 7 once
# release-appstore.sh is ported from TellUs — no App Store submission this
# early, and the AppIcon slot has no image yet either (see project.yml).
