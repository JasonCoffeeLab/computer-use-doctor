import Foundation
import AppKit
@main struct TimeoutSmoke {
    @MainActor static func main() async {
        let model=Model.shared
        let start=Date()
        model.input="transport timeout";model.classify()
        for _ in 0..<550 {
            if !model.busy { break }
            try? await Task.sleep(nanoseconds:100_000_000)
        }
        guard !model.busy, model.classification != nil, model.eventWarning != nil else {
            print("FAIL: metadata timeout blocked model or lost main result");exit(1)
        }
        print("PASS: delayed metadata helper bounded; main classification retained; warning shown. Elapsed \(Date().timeIntervalSince(start)) seconds. Fixture only.")
    }
}
