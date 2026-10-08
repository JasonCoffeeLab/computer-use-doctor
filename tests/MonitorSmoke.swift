import Foundation
import AppKit

@main struct MonitorSmoke {
    @MainActor static func settle(_ model: Model) async throws {
        for _ in 0..<400 {
            if !model.busy { return }
            try await Task.sleep(nanoseconds:50_000_000)
        }
        throw NSError(domain:"Test",code:1,userInfo:[NSLocalizedDescriptionKey:"scheduler timeout"])
    }
    @MainActor static func main() async {
        do {
            let model=Model.shared
            let missingPython=URL(fileURLWithPath:NSTemporaryDirectory()).appendingPathComponent(UUID().uuidString)
            guard !Backend.developerPythonPresent(missingPython) else { throw NSError(domain:"Test",code:31) }
            try Backend.checkPythonWithoutInstaller()
            model.readiness=EnvironmentReadiness(home:"/fixture/new-config",home_source:"explicit",config_ready:true,runtime_ready:false,rows:[],boundary:"fixture")
            guard model.configLocationText.contains("/fixture/new-config") else { throw NSError(domain:"Test",code:30) }
            model.readiness=nil
            model.check()
            try await settle(model)
            guard model.failure == nil, model.diagnostic?.repair_count == 1 else { throw NSError(domain:"Test",code:2) }
            model.enableFixtureAutomation()
            guard model.autoRepair else { throw NSError(domain:"Test",code:3) }
            model.monitorTick()
            // Allow post-check eligibility work to enter the actor queue.
            try await Task.sleep(nanoseconds:200_000_000);try await settle(model)
            guard model.diagnostic?.repair_count == 1 else { throw NSError(domain:"Test",code:4) }
            guard let i=CommandLine.arguments.firstIndex(of:"--home") else { throw NSError(domain:"Test",code:6) }
            let home=URL(fileURLWithPath:CommandLine.arguments[i+1])
            let config=home.appendingPathComponent("config.toml")
            let saved=try Data(contentsOf:config)
            try Data("[broken".utf8).write(to:config)
            model.monitorTick()
            try await Task.sleep(nanoseconds:200_000_000);try await settle(model)
            guard model.failure != nil, !model.diagnosticIsCurrent else { throw NSError(domain:"Test",code:9) }
            let failedReport=try JSONSerialization.jsonObject(with:Data(model.reportText.utf8)) as! [String:Any]
            guard failedReport["diagnostic_is_current"] as? Bool == false,
                  (failedReport["latest_check_attempt"] as? [String:Any])?["outcome"] as? String == "failed",
                  failedReport["latest_diagnostic"] != nil else { throw NSError(domain:"Test",code:13) }
            try saved.write(to:config)
            model.monitorTick()
            try await Task.sleep(nanoseconds:200_000_000);try await settle(model)
            guard model.diagnosticIsCurrent, model.diagnostic?.repair_count == 1 else { throw NSError(domain:"Test",code:10) }
            model.monitorTick()
            try await Task.sleep(nanoseconds:200_000_000);try await settle(model)
            guard model.failure == nil, model.diagnostic?.repair_count == 0 else { throw NSError(domain:"Test",code:5) }
            let repairedReport=try JSONSerialization.jsonObject(with:Data(model.reportText.utf8)) as! [String:Any]
            guard repairedReport["latest_mutation"] != nil,
                  repairedReport["latest_diagnostic"] != nil,
                  model.lastCheckAttempt?.outcome == "returned",
                  !model.events.isEmpty else { throw NSError(domain:"Test",code:14) }
            let receipts=try FileManager.default.contentsOfDirectory(at:home.appendingPathComponent("computer-use-doctor-v3/receipts"),includingPropertiesForKeys:nil).filter{$0.pathExtension=="json"}
            guard receipts.count == 1 else { throw NSError(domain:"Test",code:7) }
            model.monitorTick()
            try await Task.sleep(nanoseconds:200_000_000);try await settle(model)
            let after=try FileManager.default.contentsOfDirectory(at:home.appendingPathComponent("computer-use-doctor-v3/receipts"),includingPropertiesForKeys:nil).filter{$0.pathExtension=="json"}
            guard after.count == 1 else { throw NSError(domain:"Test",code:8) }
            model.pauseAutomationForRestore()
            guard !model.autoRepair else { throw NSError(domain:"Test",code:11) }
            model.execute("repair", extra:["--plan","invalid","--confirmed"]) { _ in }
            try await settle(model)
            guard model.failure != nil, !model.diagnosticIsCurrent else { throw NSError(domain:"Test",code:12) }
            model.check();try await settle(model)
            model.enableFixtureAutomation()
            try Data("[plugins.\"browser@openai-bundled\"]\nenabled=false\n".utf8).write(to:config)
            model.monitorTick();try await settle(model)
            guard !model.autoRepair else { throw NSError(domain:"Test",code:15) }
            let pending=home.appendingPathComponent("computer-use-doctor-v3/receipts/aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa.json")
            try Data("{\"transaction\":\"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa\",\"status\":\"prepared\",\"created_at\":\"\",\"receipts\":[]}".utf8).write(to:pending)
            model.check();try await settle(model)
            guard model.blockedTransactions.count == 1,
                  model.reportText.contains("prepared") else { throw NSError(domain:"Test",code:16) }
            let many=(0..<500).map { n in Transaction(transaction:String(format:"%032x",n+1),status:"cache_repaired",count:1,created_at:"2026-10-08T00:00:00+00:00",steps:["browser: complete"]) }
            let d=model.diagnostic!
            let large=Diagnostic(version:d.version,generated_at:d.generated_at,plugins:d.plugins,mcp:d.mcp,network:d.network,browser:d.browser,repair_count:d.repair_count,plan_id:d.plan_id,boundary:d.boundary,approval_sources:d.approval_sources,transaction_history:many,probes_completed:d.probes_completed)
            let compact=AutoRequest(current:AutoCurrent(large),previous_plan:large.plan_id,approved_sources:large.approval_sources,attempted_plans:[],cooldown:false)
            let compactData=try JSONEncoder().encode(compact)
            guard compactData.count < 64000 else { throw NSError(domain:"Test",code:17) }
            _=try Backend.run("auto-decision",input:String(decoding:compactData,as:UTF8.self))
            model.input="transport timeout";model.classify();try await settle(model)
            guard model.classification?.matches.contains(where:{$0.kind=="transport"}) == true else { throw NSError(domain:"Test",code:18) }
            model.input="changed input"
            guard model.classification == nil else { throw NSError(domain:"Test",code:19) }
            let eventFile=home.appendingPathComponent("computer-use-doctor-v3/events-v6.json")
            let originalEvents=try Data(contentsOf:eventFile)
            try Data("broken".utf8).write(to:eventFile)
            model.loadEvents();try await settle(model)
            guard model.eventWarning != nil else { throw NSError(domain:"Test",code:20) }
            try originalEvents.write(to:eventFile)
            model.loadEvents();try await settle(model)
            guard model.eventWarning == nil else { throw NSError(domain:"Test",code:21) }
            guard Section.allCases.count == 4, !model.diagnostic!.network.contains(where:{$0.name.contains("代理")}) else { throw NSError(domain:"Test",code:22) }
            model.input="transport timeout";model.classify();model.input="changed during analysis"
            try await settle(model)
            guard model.classification == nil else { throw NSError(domain:"Test",code:23) }
            model.check();try await settle(model)
            guard model.runtimeVerification?.state == "blocked", model.testActive == false, model.readiness?.config_ready == true else { throw NSError(domain:"Test",code:24) }
            model.testActive=true
            ["清除","1","加號","1","等號"].forEach { model.testPress($0) }
            guard model.testClicks == 5, model.testExpression == "1 + 1", model.testResult == "2" else { throw NSError(domain:"Test",code:25) }
            model.testActive=false;model.testPress("清除")
            guard model.testClicks == 5 else { throw NSError(domain:"Test",code:26) }
            let a=home.appendingPathComponent("First.app"),b=home.appendingPathComponent("Second.app")
            for bundle in [a,b] {
                try FileManager.default.createDirectory(at:bundle.appendingPathComponent("Contents/Resources"),withIntermediateDirectories:true)
                try FileManager.default.createDirectory(at:bundle.appendingPathComponent("Contents/MacOS"),withIntermediateDirectories:true)
                let plist:[String:Any]=["CFBundleIdentifier":"org.computer-use-doctor.preview.v9","CFBundleVersion":"801","CFBundleExecutable":"ComputerUseDoctor","CFBundlePackageType":"APPL"]
                try PropertyListSerialization.data(fromPropertyList:plist,format:.xml,options:0).write(to:bundle.appendingPathComponent("Contents/Info.plist"))
                for file in ["Contents/MacOS/ComputerUseDoctor","Contents/Resources/backend.py","Contents/Resources/runtime_client.py","Contents/Resources/install_paths.py","Contents/Resources/repair_core.py","Contents/Resources/preflight.py"] { try Data("same fixture".utf8).write(to:bundle.appendingPathComponent(file)) }
            }
            guard model.installedCopyMatches(a,b) else { throw NSError(domain:"Test",code:27) }
            try Data("different".utf8).write(to:b.appendingPathComponent("Contents/Resources/backend.py"))
            guard !model.installedCopyMatches(a,b) else { throw NSError(domain:"Test",code:28) }
            print("PASS: startup handoff requires matching bundle identity, build, executable and backend resources; modified target rejected. Synthetic fixtures only.")
            print("PASS: V9 manual check enters runtime verification; disabled fixture rejected, test panel logic and inactive protection passed. No real UI success claimed.")
            print("PASS: V7 previous protections plus 500-history compact request, input invalidation during/after analysis, recovered-event warning, consolidated navigation and no proxy rows; fixture only. Compact bytes: \(compactData.count)")
        } catch {
            print("FAIL: native monitor smoke: \(error)");exit(1)
        }
    }
}
