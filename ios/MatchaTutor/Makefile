.PHONY: generate open build clean

# Generate Xcode project from project.yml
generate:
	@which xcodegen > /dev/null || (echo "Installing XcodeGen..." && brew install xcodegen)
	xcodegen generate

# Open project in Xcode
open: generate
	open MatchaTutor.xcodeproj

# Build for simulator
build:
	xcodebuild build \
		-scheme MatchaTutor \
		-destination 'platform=iOS Simulator,name=iPhone 15 Pro' \
		-configuration Debug

# Clean build artifacts
clean:
	xcodebuild clean -scheme MatchaTutor
	rm -rf build/
	rm -rf DerivedData/

# Install dependencies (XcodeGen)
deps:
	brew install xcodegen

# Run on simulator
run: generate
	xcodebuild build \
		-scheme MatchaTutor \
		-destination 'platform=iOS Simulator,name=iPhone 15 Pro' \
		-configuration Debug \
		| xcpretty
	xcrun simctl boot "iPhone 15 Pro" 2>/dev/null || true
	xcrun simctl install "iPhone 15 Pro" build/Debug-iphonesimulator/MatchaTutor.app
	xcrun simctl launch "iPhone 15 Pro" com.matcha.tutor
