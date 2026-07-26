import Foundation

private extension Data {
    mutating func append(_ string: String) {
        if let d = string.data(using: .utf8) { append(d) }
    }
}

/// Builds a `multipart/form-data` request body matching what the backend
/// `aiohttp` parser expects. Boundary is randomized per builder.
///
/// Usage:
/// ```
/// var b = MultipartUploadBuilder()
/// b.addField(name: "title", value: "hello")
/// b.addFile(name: "files", filename: "x.png", mimeType: "image/png", data: png)
/// let (body, contentType) = b.finalize()
/// request.setValue(contentType, forHTTPHeaderField: "Content-Type")
/// request.httpBody = body
/// ```
struct MultipartUploadBuilder {
    let boundary: String
    private var body = Data()

    init(boundary: String = "Boundary-\(UUID().uuidString)") {
        self.boundary = boundary
    }

    mutating func addField(name: String, value: String) {
        body.append("--\(boundary)\r\n")
        body.append("Content-Disposition: form-data; name=\"\(name)\"\r\n\r\n")
        body.append(value)
        body.append("\r\n")
    }

    mutating func addFile(name: String, filename: String, mimeType: String, data: Data) {
        body.append("--\(boundary)\r\n")
        body.append("Content-Disposition: form-data; name=\"\(name)\"; filename=\"\(filename)\"\r\n")
        body.append("Content-Type: \(mimeType)\r\n\r\n")
        body.append(data)
        body.append("\r\n")
    }

    /// Returns the final body bytes and the `Content-Type` header value.
    /// After calling this the builder should not be reused.
    func finalize() -> (body: Data, contentType: String) {
        var out = body
        out.append("--\(boundary)--\r\n")
        return (out, "multipart/form-data; boundary=\(boundary)")
    }
}
