.PHONY: generate build test open

generate:
	xcodegen generate

build:
	../../../scripts/xcode-build.sh matchaschedule build

test:
	XCODE_DESTINATION="$${XCODE_DESTINATION:-platform=iOS Simulator,name=iPhone 16}" ../../../scripts/xcode-build.sh matchaschedule test

open: generate
	open MatchaSchedule.xcodeproj
