SIM ?= iPhone 17 Pro

.PHONY: generate open build test clean run deps

generate:
	@which xcodegen > /dev/null || (echo "Installing XcodeGen..." && brew install xcodegen)
	xcodegen generate

open: generate
	open TellUs.xcodeproj

build: generate
	xcodebuild build \
		-scheme TellUs \
		-destination 'platform=iOS Simulator,name=$(SIM)' \
		-configuration Debug

test: generate
	xcodebuild test \
		-scheme TellUs \
		-destination 'platform=iOS Simulator,name=$(SIM)' \
		-configuration Debug

clean:
	xcodebuild clean -scheme TellUs
	rm -rf build/
	rm -rf DerivedData/

deps:
	brew install xcodegen

run: build
	xcrun simctl boot "$(SIM)" 2>/dev/null || true
	xcrun simctl install "$(SIM)" build/Debug-iphonesimulator/TellUs.app
	xcrun simctl launch "$(SIM)" com.matcha.tellus
