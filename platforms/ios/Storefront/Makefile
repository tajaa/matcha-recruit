SIM ?= iPhone 17 Pro
SCHEME ?= Ahnimal

.PHONY: generate open build test run clean release release-dry

generate:
	@command -v xcodegen >/dev/null || (echo "Install XcodeGen first: brew install xcodegen" && exit 1)
	xcodegen generate

open: generate
	open Storefront.xcodeproj

build: generate
	xcodebuild build -project Storefront.xcodeproj -scheme "$(SCHEME)" -configuration Debug -destination 'platform=iOS Simulator,name=$(SIM)' CODE_SIGNING_ALLOWED=NO

test: generate
	xcodebuild test -project Storefront.xcodeproj -scheme "$(SCHEME)" -configuration Debug -destination 'platform=iOS Simulator,name=$(SIM)' CODE_SIGNING_ALLOWED=NO

run:
	SIM="$(SIM)" SCHEME="$(SCHEME)" ./run.sh

clean:
	xcodebuild clean -project Storefront.xcodeproj -scheme "$(SCHEME)"
	rm -rf build

release:
	./release-appstore.sh

release-dry:
	./release-appstore.sh --no-upload
