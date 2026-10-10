import XCTest

/// Signs in and captures every main screen as a kept test attachment, for
/// design review. Opt-in: needs the local backend running and credentials in
/// the runner environment (TEST_RUNNER_MATCHA_UI_EMAIL / _PASSWORD when run
/// through xcodebuild). Without them it captures the sign-in screen and skips.
/// A manager account also tours Manage (approvals, the week, a shift, the
/// people picker, a new shift) without saving anything.
/// TEST_RUNNER_MATCHA_UI_API_URL points the app at another backend.
final class ScreenTour: XCTestCase {
    private var app: XCUIApplication!

    override func setUp() {
        continueAfterFailure = true
        app = XCUIApplication()
        if let api = ProcessInfo.processInfo.environment["MATCHA_UI_API_URL"], !api.isEmpty {
            app.launchEnvironment["MATCHA_API_URL"] = api
        }
        app.launch()
    }

    func testCaptureScreens() throws {
        let env = ProcessInfo.processInfo.environment
        let tabs = app.tabBars.firstMatch
        let email = app.textFields["login.email"].exists ? app.textFields["login.email"] : app.textFields["Email"]

        if !tabs.waitForExistence(timeout: 4) {
            XCTAssertTrue(email.waitForExistence(timeout: 10), "neither tabs nor sign-in appeared")
            pause(1.2)
            snap("01-sign-in")
            guard let user = env["MATCHA_UI_EMAIL"], let pass = env["MATCHA_UI_PASSWORD"] else {
                throw XCTSkip("No MATCHA_UI_EMAIL / MATCHA_UI_PASSWORD; captured sign-in only")
            }
            email.tap()
            email.typeText(user)
            let password = app.secureTextFields["login.password"].exists
                ? app.secureTextFields["login.password"] : app.secureTextFields["Password"]
            password.tap()
            password.typeText(pass)
            let submit = app.buttons["login.submit"].exists ? app.buttons["login.submit"] : app.buttons["Sign in"]
            submit.tap()
            allowNotificationsIfAsked()
            XCTAssertTrue(tabs.waitForExistence(timeout: 20), "sign-in did not reach the app")
        }
        allowNotificationsIfAsked()
        dismissSavePasswordIfAsked()

        pause(3)
        // A business admin has no shifts of their own: no Schedule or Requests tab.
        guard app.tabBars.buttons["Schedule"].exists else {
            snap("02-manage-first")
            tourManage()
            open(tab: "Me")
            snap("07-me")
            return
        }
        snap("02-schedule")
        // Demo data may sit in past weeks: MATCHA_UI_WEEKS_BACK pages back to it.
        let weeksBack = Int(env["MATCHA_UI_WEEKS_BACK"] ?? "") ?? 0
        if weeksBack > 0 {
            let previous = app.buttons["week.previous"]
            for _ in 0..<weeksBack where previous.waitForExistence(timeout: 2) {
                previous.tap()
                pause(0.6)
            }
            pause(2.5)
            snap("02b-schedule-week")
            app.swipeUp()
            pause(1)
            snap("02c-schedule-scrolled")
            app.swipeDown()
            pause(0.8)
        }
        let shift = app.buttons.matching(identifier: "shift.row").firstMatch
        if shift.waitForExistence(timeout: 3) {
            shift.tap()
            pause(1.5)
            snap("03-shift-detail")
            if app.buttons["Done"].exists { app.buttons["Done"].tap() } else { app.swipeDown() }
            pause(1)
        }

        open(tab: "Requests")
        snap("04-requests")

        open(tab: "Messages")
        snap("05-messages")
        let conversation = app.buttons.matching(identifier: "conversation.row").firstMatch
        if conversation.waitForExistence(timeout: 3) {
            conversation.tap()
            pause(2)
            snap("06-thread")
            app.navigationBars.buttons.firstMatch.tap()
            pause(1)
        }

        if app.tabBars.buttons["Manage"].exists { tourManage() }

        open(tab: "Me")
        snap("07-me")
        let dark = app.buttons["appearance.dark"]
        if dark.waitForExistence(timeout: 2) {
            app.swipeUp()
            pause(0.6)
            dark.tap()
            pause(1.2)
            snap("07b-me-dark")
            open(tab: "Schedule")
            snap("07c-schedule-dark")
            open(tab: "Me")
            app.swipeUp()
            pause(0.6)
            app.buttons["appearance.system"].tap()
            pause(1)
            app.swipeDown()
            pause(0.6)
        }
        let bell = app.buttons.matching(identifier: "me.notifications").firstMatch
        if bell.waitForExistence(timeout: 2) {
            bell.tap()
            pause(2)
            snap("08-notifications")
        }
    }

    /// Looks at every manager screen and backs out of each; saves nothing.
    private func tourManage() {
        open(tab: "Manage")
        snap("09-manage-approvals")
        let request = app.buttons.matching(identifier: "approvals.request").firstMatch
        if request.waitForExistence(timeout: 2) {
            request.tap()
            pause(1.5)
            snap("09b-review")
            app.buttons["Close"].tap()
            pause(1)
        }
        let week = app.segmentedControls.buttons["Week"]
        guard week.waitForExistence(timeout: 2) else { return }
        week.tap()
        pause(3)
        snap("10-manage-week")
        let shift = app.buttons.matching(identifier: "week.shift").firstMatch
        if shift.waitForExistence(timeout: 3) {
            shift.tap()
            pause(1.5)
            snap("10b-manage-shift")
            let add = app.buttons["shift.addPerson"]
            if add.waitForExistence(timeout: 2) {
                add.tap()
                pause(2.5)
                snap("10c-manage-picker")
                app.buttons["Cancel"].firstMatch.tap()
                pause(1)
            }
            app.buttons["Done"].firstMatch.tap()
            pause(1)
        }
        let addShift = app.buttons["week.addShift"]
        if addShift.waitForExistence(timeout: 2) {
            addShift.tap()
            pause(1.5)
            snap("10d-manage-new-shift")
            app.buttons["Cancel"].firstMatch.tap()
            pause(1)
        }
    }

    private func dismissSavePasswordIfAsked() {
        for candidate in [app.buttons["Not Now"], XCUIApplication(bundleIdentifier: "com.apple.springboard").buttons["Not Now"]] {
            if candidate.waitForExistence(timeout: 2) { candidate.tap(); pause(0.8); return }
        }
    }

    private func open(tab name: String) {
        app.tabBars.buttons[name].firstMatch.tap()
        pause(2.5)
    }

    private func allowNotificationsIfAsked() {
        let springboard = XCUIApplication(bundleIdentifier: "com.apple.springboard")
        let allow = springboard.alerts.buttons["Allow"]
        if allow.waitForExistence(timeout: 3) { allow.tap() }
    }

    private func pause(_ seconds: TimeInterval) {
        _ = XCTWaiter.wait(for: [XCTestExpectation(description: "settle")], timeout: seconds)
    }

    private func snap(_ name: String) {
        let attachment = XCTAttachment(screenshot: XCUIScreen.main.screenshot())
        attachment.name = name
        attachment.lifetime = .keepAlways
        add(attachment)
    }
}
