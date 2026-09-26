import XCTest
@testable import MatchaSchedule

final class RequestModelsTests: XCTestCase {
    func testOfferAndRequestPayloadsDecode() throws {
        let json = """
        {"offers":[{"id":"offer","employee_id":"owner","employee_name":"Ava",
          "request_type":"swap","status":"awaiting_counterparty","shift_id":"shift",
          "shift_starts_at":"2026-09-23T09:00:00+00:00","shift_role":"Barista",
          "target_employee_id":"me","counter_shift_id":"counter",
          "created_at":"2026-09-20T10:00:00+00:00"}]}
        """
        let offer = try JSONDecoder().decode(OffersResponse.self, from: Data(json.utf8)).offers[0]
        XCTAssertEqual(offer.counter_shift_id, "counter")
        XCTAssertTrue(offer.isPending)
        XCTAssertEqual(offer.target_employee_id, "me")
    }

    func testClaimRequestEncodesOnlyExpectedFields() throws {
        let body = ScheduleRequestBody(request_type: "claim", shift_id: "shift",
                                       target_employee_id: nil, counter_shift_id: nil,
                                       unavailable_start: nil, unavailable_end: nil, reason: nil)
        let value = try JSONSerialization.jsonObject(with: JSONEncoder().encode(body)) as! [String: Any]
        XCTAssertEqual(value["request_type"] as? String, "claim")
        XCTAssertEqual(value["shift_id"] as? String, "shift")
        XCTAssertNil(value["target_employee_id"])
    }

    func testAvailabilityAndPTOShapesDecode() throws {
        let availability = """
        {"availability_state":"windows","windows":[{"weekday":1,"start_time":"09:00","end_time":"17:00"}],"pending_request":null}
        """
        let current = try JSONDecoder().decode(AvailabilityResponse.self, from: Data(availability.utf8))
        XCTAssertEqual(current.windows.first?.weekday, 1)
        let pto = """
        {"balance":{"balance_hours":"40.0"},"pending_requests":[{"id":"pto","start_date":"2026-09-25",
          "end_date":"2026-09-26","hours":"16.0","reason":null,"request_type":"vacation",
          "status":"pending","denial_reason":null}],"approved_requests":[]}
        """
        let summary = try JSONDecoder().decode(PTOSummary.self, from: Data(pto.utf8))
        XCTAssertEqual(summary.balance.balance_hours, "40.0")
        XCTAssertEqual(summary.pending_requests.first?.hours, "16.0")
    }
}
