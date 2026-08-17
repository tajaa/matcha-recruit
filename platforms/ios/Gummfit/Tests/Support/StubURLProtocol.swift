import Foundation

final class StubURLProtocol: URLProtocol {
    static var statusCode = 200
    static var responseBody = Data()
    static var chunks: [Data] = []

    override class func canInit(with request: URLRequest) -> Bool { true }
    override class func canonicalRequest(for request: URLRequest) -> URLRequest { request }

    override func startLoading() {
        guard let client else { return }
        let response = HTTPURLResponse(
            url: request.url!, statusCode: Self.statusCode,
            httpVersion: nil, headerFields: ["Content-Type": "text/event-stream"]
        )!
        client.urlProtocol(self, didReceive: response, cacheStoragePolicy: .notAllowed)
        let payloads = Self.chunks.isEmpty ? [Self.responseBody] : Self.chunks
        for payload in payloads where !payload.isEmpty {
            client.urlProtocol(self, didLoad: payload)
        }
        client.urlProtocolDidFinishLoading(self)
    }

    override func stopLoading() {}
}
