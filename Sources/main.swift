import SwiftUI
import AppKit
import UniformTypeIdentifiers
import ServiceManagement
import CryptoKit
import ApplicationServices
import CoreGraphics

struct DiagnosticRow: Codable, Identifiable {
    var id: String { name }
    let name: String
    let state: String
    let detail: String
    var version: String?
    var repairable: Bool?
    var enabled: Bool?
}
struct SourceApproval: Codable, Equatable { let version: String?; let hash: String; let enabled: Bool }
struct RuntimeVerification: Codable {
    let state: String; let phase: String; let detail: String; let route: String
    let generated_at: String; let nonce: String; let clicks: Int; let screenshot: String
}
struct EnvironmentReadiness: Codable {
    let home: String; let home_source: String
    let config_ready: Bool; let runtime_ready: Bool
    let rows: [DiagnosticRow]; let boundary: String
}
struct Diagnostic: Codable {
    let version: String
    let generated_at: String
    let plugins: [DiagnosticRow]
    let mcp: [DiagnosticRow]
    let network: [DiagnosticRow]
    let browser: [DiagnosticRow]
    let repair_count: Int
    let plan_id: String
    let boundary: String
    let approval_sources: [String: SourceApproval]
    let transaction_history: [Transaction]
    let probes_completed: Bool
}
struct AutoRequest: Encodable {
    let current: AutoCurrent
    let previous_plan: String?
    let approved_sources: [String: SourceApproval]
    let attempted_plans: [String]
    let cooldown: Bool
}
struct AutoCurrent: Encodable {
    let repair_count: Int; let plan_id: String
    let approval_sources: [String:SourceApproval]
    let transaction_blocked: Bool
    init(_ d:Diagnostic) {
        repair_count=d.repair_count;plan_id=d.plan_id;approval_sources=d.approval_sources
        transaction_blocked=d.transaction_history.contains{!["cache_repaired","restored","no_changes"].contains($0.status)}
    }
}
struct AutoDecision: Decodable { let eligible: Bool; let reason: String; let pause: Bool? }
struct OperationAttempt: Codable {
    let action: String; let outcome: String; let time: String; let error: String?
}
struct EventRow: Codable, Identifiable {
    var id: String { created_at + action + code }
    let created_at: String; let action: String; let code: String
    var title: String {
        let actions=["diagnose":"診斷","repair":"快取修復","restore":"備份恢復","classify":"本機文字分類","history":"交易讀取","auto-decision":"自動修復判斷"]
        let outcomes=["returned":"已返回","failed":"未完成","scope_changed":"範圍改變，已暫停","transaction_blocked":"交易待核對","no_fault":"沒有可修快取問題","waiting":"等待穩定觀察","same_plan":"同方案不重做","cooldown":"冷卻中","eligible":"符合限定修復條件"]
        return "\(actions[action] ?? action)：\(outcomes[code] ?? code)"
    }
}
struct Classification: Decodable {
    struct Match: Decodable, Identifiable {
        var id: String { kind }
        let kind: String
        let title: String
        let next_step: String
    }
    let matches: [Match]
    let boundary: String
}
struct Transaction: Codable, Identifiable {
    var id: String { transaction }
    let transaction: String
    let status: String
    let count: Int
    let created_at: String
    let steps: [String]
}
enum Section: String, CaseIterable, Identifiable {
    case overview = "檢查與修復", backups = "備份與恢復", events = "處理紀錄", report = "診斷報告"
    var id: String { rawValue }
    var icon: String {
        switch self {
        case .overview: return "square.grid.2x2"
        case .backups: return "clock.arrow.circlepath"
        case .events: return "list.bullet.rectangle"
        case .report: return "doc.text"
        }
    }
}

enum Backend {
    static func developerPythonPresent(_ directory:URL) -> Bool {
        FileManager.default.isExecutableFile(atPath:directory.appendingPathComponent("usr/bin/python3").path)
    }
    static func checkPythonWithoutInstaller() throws {
        let probe=Process();let output=Pipe()
        probe.executableURL=URL(fileURLWithPath:"/usr/bin/xcode-select");probe.arguments=["-p"]
        probe.standardOutput=output;probe.standardError=FileHandle.nullDevice
        try probe.run()
        let data=output.fileHandleForReading.readDataToEndOfFile();probe.waitUntilExit()
        let selected=String(decoding:data,as:UTF8.self).trimmingCharacters(in:.whitespacesAndNewlines)
        guard probe.terminationStatus == 0, selected.hasPrefix("/"), developerPythonPresent(URL(fileURLWithPath:selected)) else {
            throw NSError(domain:"Doctor",code:31,userInfo:[NSLocalizedDescriptionKey:"未找到可用的系統 Python 執行環境；請由本人準備免費的 Apple Command Line Tools。未啟動 Python 安裝提示、不自動下載，也不需要付費 Apple Developer 帳號。"])
        }
    }
    static func run(_ action: String, extra: [String] = [], input: String? = nil, configHome: String? = nil) throws -> Data {
        if let input = input, input.utf8.count > 64000 {
            throw NSError(domain: "V9", code: 10, userInfo: [NSLocalizedDescriptionKey: "記錄超過64KB，請按相關事件分段；未默默截斷。"])
        }
        guard let resource = Bundle.main.resourceURL else {
            throw NSError(domain: "V3", code: 1, userInfo: [NSLocalizedDescriptionKey: "App 資源缺失"])
        }
        let script = resource.appendingPathComponent("backend.py")
        guard FileManager.default.fileExists(atPath: script.path), FileManager.default.isExecutableFile(atPath: "/usr/bin/python3") else {
            throw NSError(domain: "V3", code: 2, userInfo: [NSLocalizedDescriptionKey: "需要本機 Python 3，或 App 資源不完整。未自動下載／安裝。"])
        }
        try checkPythonWithoutInstaller()
        let process = Process()
        process.executableURL = URL(fileURLWithPath: "/usr/bin/python3")
        var arguments = [script.path, action] + extra
        if let configHome=configHome { arguments += ["--home",configHome] }
        // Fixture override is excluded from production builds.
        #if TESTING
        if CommandLine.arguments.contains("--fixture") {
            if let index = CommandLine.arguments.firstIndex(of: "--home"), index + 1 < CommandLine.arguments.count {
                arguments += ["--home", CommandLine.arguments[index + 1], "--no-probe"]
            }
        }
        #endif
        process.arguments = arguments
        var environment = ProcessInfo.processInfo.environment
        environment["PYTHONDONTWRITEBYTECODE"] = "1"
        environment["PYTHONNOUSERSITE"] = "1"
        environment.removeValue(forKey: "PYTHONPATH")
        environment.removeValue(forKey: "PYTHONHOME")
        process.environment = environment
        let out = Pipe(), error = Pipe(), stdin = Pipe()
        process.standardOutput = out; process.standardError = error; process.standardInput = stdin
        try process.run()
        // Bound reads and the atomic metadata journal; never kill a cache repair/restore.
        let cancellable = ["preflight", "diagnose", "classify", "history", "auto-decision", "event-history", "record-event"].contains(action)
        let watchdog = DispatchWorkItem { if process.isRunning { process.terminate() } }
        if cancellable { DispatchQueue.global().asyncAfter(deadline: .now() + 45, execute: watchdog) }
        if let input = input { stdin.fileHandleForWriting.write(input.data(using: .utf8) ?? Data()) }
        try? stdin.fileHandleForWriting.close()
        // Drain stderr independently to avoid filling a pipe during long work.
        let stderrGroup = DispatchGroup()
        stderrGroup.enter()
        DispatchQueue.global().async { _ = error.fileHandleForReading.readDataToEndOfFile(); stderrGroup.leave() }
        let data = out.fileHandleForReading.readDataToEndOfFile()
        process.waitUntilExit(); stderrGroup.wait()
        watchdog.cancel()
        if cancellable && process.terminationReason == .uncaughtSignal {
            if action == "record-event" { throw NSError(domain:"V9",code:12,userInfo:[NSLocalizedDescriptionKey:"事件保存逾時或中斷；結果需核對，不將主操作當成失敗或保證紀錄未寫入。"] ) }
            throw NSError(domain: "V9", code: 11, userInfo: [NSLocalizedDescriptionKey: "只讀檢查超時或中斷；原因未確認，不判定缺授權，也未修改快取。"])
        }
        guard let object = try JSONSerialization.jsonObject(with: data) as? [String: Any], let ok = object["ok"] as? Bool else {
            throw NSError(domain: "V3", code: 3, userInfo: [NSLocalizedDescriptionKey: "後端沒有返回有效報告；未把原始錯誤或配置內容顯示出來。"])
        }
        if !ok {
            throw NSError(domain: "V3", code: 4, userInfo: [NSLocalizedDescriptionKey: object["error"] as? String ?? "操作失敗，請核對交易記錄。"])
        }
        return try JSONSerialization.data(withJSONObject: object["data"] ?? [:], options: [.prettyPrinted, .sortedKeys])
    }
}

@MainActor final class Model: ObservableObject {
    static let shared = Model()
    @Published var section: Section? = .overview
    @Published var diagnostic: Diagnostic?
    @Published var classification: Classification?
    @Published var transactions: [Transaction] = []
    @Published var input = "" { didSet { if input != oldValue { classification=nil } } }
    @Published var rawReport = "尚未檢查。點擊「開始檢查」；此動作不修改配置或快取。"
    @Published var status = "準備就緒"
    @Published var busy = false
    @Published var failure: String?
    @Published var autoCheck = true
    @Published private(set) var autoRepair = false
    @Published var automationStatus = "自動檢查已開啟；自動修復尚未啟用"
    @Published var lastCheck = "尚未檢查"
    @Published var lastAttempt: OperationAttempt?
    @Published var lastCheckAttempt: OperationAttempt?
    @Published var lastFailure: OperationAttempt?
    @Published var events: [EventRow] = []
    @Published var eventWarning: String?
    @Published var startupEnabled=false
    @Published var startupStatus="登入自啟動尚未核對"
    @Published var instanceStatus=""
    @Published var installedVersionAvailable=false
    @Published var accessibilityAllowed=false
    @Published var screenCaptureAllowed=false
    @Published var readiness: EnvironmentReadiness?
    @Published var configPathInput=""
    @Published private(set) var configHome: String? = UserDefaults.standard.string(forKey:"doctorConfigHome")
    var configLocationText:String {
        if let readiness=readiness { return "正在使用：\(readiness.home)（\(readiness.home_source)）" }
        if let configHome=configHome { return "已指定：\(configHome)；尚待核對，不退回其他設定。" }
        return "尚未取得有效環境。依 CODEX_HOME 或預設 .codex；不搜尋其他帳號。"
    }
    func chooseConfigFolder() {
        guard !busy else { return }
        let panel=NSOpenPanel()
        panel.canChooseDirectories=true;panel.canChooseFiles=false;panel.allowsMultipleSelection=false
        panel.canCreateDirectories=false;panel.allowedContentTypes=[.folder];panel.prompt="選擇資料夾"
        panel.message="選擇你自己的 Codex 設定資料夾（內含 config.toml）。只改 Doctor 的選擇，不複製登入資料或修改 Codex 設定。"
        dialogOpen=true
        panel.begin { response in
            Task { @MainActor in
                self.dialogOpen=false
                guard response == .OK, let url=panel.url else { return }
                self.configHome=url.resolvingSymlinksInPath().path
                UserDefaults.standard.set(self.configHome,forKey:"doctorConfigHome")
                self.resetEnvironment()
            }
        }
    }
    func applyConfigPath() {
        guard !busy, !dialogOpen else { return }
        let candidate=configPathInput.trimmingCharacters(in:.whitespacesAndNewlines)
        guard !candidate.isEmpty else { failure="設定路徑不可留空；未切換設定。";return }
        configHome=candidate;UserDefaults.standard.set(candidate,forKey:"doctorConfigHome")
        resetEnvironment()
    }
    func useDefaultConfigFolder() {
        guard !busy else { return }
        configHome=nil;UserDefaults.standard.removeObject(forKey:"doctorConfigHome")
        resetEnvironment()
    }
    func resetEnvironment() {
        timer?.invalidate();timer=nil;started=false
        autoRepair=false;approvedSources=[:];previousPlan=nil;attemptedPlans.removeAll()
        readiness=nil;diagnostic=nil;diagnosticIsCurrent=false;transactions=[];events=[]
        runtimeVerification=nil;diagnosticReport="";mutationReport="";eventWarning=nil
        testActive=false;testNonce="尚未啟動";testClicks=0;testResult="待測";testExpression="待測"
        lastAttempt=nil;lastCheckAttempt=nil;lastFailure=nil;lastCheck="尚未檢查"
        automationStatus="設定目錄已切換；舊診斷與本次自動修復授權已清除，重新檢查後才可修復。"
        startMonitoring()
    }
    func readNativePermissions() {
        #if !TESTING
        accessibilityAllowed=AXIsProcessTrusted()
        screenCaptureAllowed=CGPreflightScreenCaptureAccess()
        UserDefaults.standard.set(accessibilityAllowed,forKey:"nativeAccessibilityObserved")
        UserDefaults.standard.set(screenCaptureAllowed,forKey:"nativeScreenCaptureObserved")
        #endif
    }
    func openPermissionSettings(_ screen:Bool) {
        let pane=screen ? "Privacy_ScreenCapture" : "Privacy_Accessibility"
        if let url=URL(string:"x-apple.systempreferences:com.apple.preference.security?"+pane) { NSWorkspace.shared.open(url) }
    }
    var installedURL: URL {
        let current=Bundle.main.bundleURL.resolvingSymlinksInPath()
        let user=FileManager.default.homeDirectoryForCurrentUser.appendingPathComponent("Applications/Computer Use Doctor V9 Preview.app")
        let system=URL(fileURLWithPath:"/Applications/Computer Use Doctor V9 Preview.app")
        if current==system || current==user { return current }
        return installedCopyMatches(current,system) ? system : user
    }
    func installedCopyMatches(_ current:URL,_ installed:URL) -> Bool {
        guard let from=Bundle(url:current), let to=Bundle(url:installed),
              from.bundleIdentifier == "org.computer-use-doctor.preview.v9", to.bundleIdentifier==from.bundleIdentifier,
              from.object(forInfoDictionaryKey:"CFBundleVersion") as? String == to.object(forInfoDictionaryKey:"CFBundleVersion") as? String else { return false }
        for component in ["Contents/MacOS/ComputerUseDoctor","Contents/Resources/backend.py","Contents/Resources/runtime_client.py","Contents/Resources/install_paths.py","Contents/Resources/repair_core.py","Contents/Resources/preflight.py"] {
            guard let a=try? Data(contentsOf:current.appendingPathComponent(component)),
                  let b=try? Data(contentsOf:installed.appendingPathComponent(component)),
                  SHA256.hash(data:a)==SHA256.hash(data:b) else { return false }
        }
        return true
    }
    func prepareInstalledInstance() -> Bool {
        #if !TESTING
        let current=Bundle.main.bundleURL.resolvingSymlinksInPath()
        let target=installedURL.resolvingSymlinksInPath()
        if current==target {
            if let earlier=NSRunningApplication.runningApplications(withBundleIdentifier:"org.computer-use-doctor.preview.v9").first(where:{
                $0.processIdentifier < ProcessInfo.processInfo.processIdentifier && $0.bundleURL?.resolvingSymlinksInPath()==target
            }) {
                earlier.activate(options:[]);NSApplication.shared.terminate(nil);return false
            }
            let version=Bundle.main.object(forInfoDictionaryKey:"CFBundleShortVersionString") as? String ?? "未確認"
            instanceStatus="目前執行：本機 Applications 固定版本（\(version)）";return true
        }
        installedVersionAvailable=installedCopyMatches(current,target)
        instanceStatus="目前執行：收納／其他位置副本，不登記此位置。"
        if installedVersionAvailable {
            openInstalledVersion()
        } else {
            startupStatus="本機版本缺失或與這份副本不同；未猜測、覆蓋或登記收納位置。請使用本次已核對的本機版本。"
        }
        return false
        #else
        return true
        #endif
    }
    func openInstalledVersion() {
        guard !busy, installedCopyMatches(Bundle.main.bundleURL.resolvingSymlinksInPath(),installedURL.resolvingSymlinksInPath()) else {
            startupStatus="本機版本未匹配或仍有操作進行；不切換、不退出。";return
        }
        if let existing=NSRunningApplication.runningApplications(withBundleIdentifier:"org.computer-use-doctor.preview.v9").first(where:{
            $0.processIdentifier != ProcessInfo.processInfo.processIdentifier && $0.bundleURL?.resolvingSymlinksInPath()==installedURL.resolvingSymlinksInPath()
        }) {
            existing.activate(options:[]);NSApplication.shared.terminate(nil);return
        }
        let configuration=NSWorkspace.OpenConfiguration()
        configuration.activates=true
        // Same bundle ID at two paths must not resolve back to this storage copy.
        configuration.createsNewApplicationInstance=true
        NSWorkspace.shared.openApplication(at:installedURL,configuration:configuration) { app,error in
            Task { @MainActor in
                if error == nil, let app=app,
                   app.processIdentifier != ProcessInfo.processInfo.processIdentifier,
                   app.bundleURL?.resolvingSymlinksInPath()==self.installedURL.resolvingSymlinksInPath() {
                    NSApplication.shared.terminate(nil)
                } else { self.startupStatus="開啟本機版本失敗；保留目前視窗，不宣稱已接續。" }
            }
        }
    }
    @Published var runtimeVerification: RuntimeVerification?
    @Published var testNonce="尚未啟動"
    @Published var testClicks=0
    @Published var testResult="待測"
    @Published var testExpression="待測"
    private var testTerms=[Int]()
    private var testAdding=false
    @Published var testActive=false
    var testStateText:String { "實測批次：\(testNonce)\n實測算式：\(testExpression)\n實測結果：\(testResult)\n實測點擊：\(testClicks)" }
    var runtimeTitle: String { runtimeVerification?.state == "passed" ? "本次操作通過" : runtimeVerification?.state == "blocked" ? "實測尚未就緒" : runtimeVerification == nil ? "尚未實測" : "本次實測失敗" }
    func testPress(_ label:String) {
        guard testActive else { return }
        testClicks += 1
        switch label {
        case "清除": testTerms=[];testAdding=false;testResult="0";testExpression="0"
        case "1": testTerms.append(1);testResult="1";testExpression=testTerms.count == 2 && testAdding ? "1 + 1" : "1"
        case "加號": testAdding=true
        case "等號": testResult=testTerms == [1,1] && testAdding ? "2" : "錯誤"
        default: break
        }
    }
    func verifyRuntime() {
        guard !busy else { return }
        readNativePermissions()
        // The configured broker owns its authorization. Doctor's direct-API flags
        // are diagnostic only, not proof of broker readiness or an authority grant.
        // The official tool must authorize each call; errors never become success.
        let nonce=UUID().uuidString
        testNonce=nonce;testClicks=0;testResult="待測";testExpression="待測";testTerms=[];testAdding=false
        runtimeVerification=nil;testActive=true
        execute("runtime-verify",extra:["--nonce",nonce,"--app-path",Bundle.main.bundleURL.path],then:{ self.testActive=false }) { data in
            let result=try JSONDecoder().decode(RuntimeVerification.self,from:data)
            guard result.nonce==nonce else { throw NSError(domain:"V9",code:20,userInfo:[NSLocalizedDescriptionKey:"實測批次不一致，不使用舊结果。"]) }
            self.runtimeVerification=result
        }
    }
    @Published private var diagnosticReport = ""
    @Published private var mutationReport = ""
    var blockedTransactions: [Transaction] {
        transactions.filter { !["cache_repaired","restored","no_changes"].contains($0.status) }
    }
    var reportText: String {
        var object: [String: Any] = ["version":"V9", "diagnostic_is_current":diagnosticIsCurrent,
            "unresolved_transactions":blockedTransactions.count, "automation_status":automationStatus,
            "auto_check":autoCheck, "auto_repair":autoRepair]
        func encoded<T: Encodable>(_ value: T) -> Any? {
            guard let data=try? JSONEncoder().encode(value) else { return nil }
            return try? JSONSerialization.jsonObject(with:data)
        }
        object["latest_attempt"]=lastAttempt.flatMap { encoded($0) }
        object["runtime_verification"]=runtimeVerification.flatMap { encoded($0) }
        object["doctor_direct_api_permissions"]=["accessibility":accessibilityAllowed,"screen_capture":screenCaptureAllowed,"used_by_current_runtime_route":false]
        object["latest_check_attempt"]=lastCheckAttempt.flatMap { encoded($0) }
        object["last_failure_historical"]=lastFailure.flatMap { encoded($0) }
        object["latest_diagnostic"]=diagnosticReport.data(using:.utf8).flatMap { try? JSONSerialization.jsonObject(with:$0) }
        object["latest_mutation"]=mutationReport.data(using:.utf8).flatMap { try? JSONSerialization.jsonObject(with:$0) }
        object["events"]=encoded(events); object["event_log_warning"]=eventWarning
        object["transaction_history"]=encoded(transactions)
        object["startup_enabled"]=startupEnabled;object["startup_status"]=startupStatus
        object["selected_environment"]=readiness.flatMap { encoded($0) }
        guard let data=try? JSONSerialization.data(withJSONObject:object,options:[.prettyPrinted,.sortedKeys]) else { return "報告無法組成；未宣稱成功。" }
        return String(decoding:data,as:UTF8.self)
    }
    @Published private(set) var diagnosticIsCurrent = false
    private var timer: Timer?
    private var approvedSources: [String: SourceApproval] = [:]
    private var previousPlan: String?
    private var attemptedPlans = Set<String>()
    private var lastRepairAt: Date?
    private var started = false
    private var mutating = false
    private var dialogOpen = false
    private var clearChecks = 0
    private func setDockBadge(_ value: String?) {
        #if !TESTING
        NSApplication.shared.dockTile.badgeLabel = value
        #endif
    }
    #if TESTING
    func enableFixtureAutomation() {
        guard CommandLine.arguments.contains("--fixture"), let d = diagnostic,
              let i = CommandLine.arguments.firstIndex(of: "--home"), i+1 < CommandLine.arguments.count else { return }
        let path=URL(fileURLWithPath:CommandLine.arguments[i+1]).resolvingSymlinksInPath().path
        guard path.hasPrefix("/private/tmp/doctor-v9-fixture-") || path.hasPrefix("/tmp/doctor-v9-fixture-") else { return }
        approveAutomation(d)
    }
    #endif
    func startMonitoring() {
        guard !started else { return }; started = true
        let installed=prepareInstalledInstance()
        readNativePermissions()
        execute("preflight",extra:["--app-path",Bundle.main.bundleURL.path],then:{ [self] in
            guard installed, self.readiness?.config_ready == true else { return }
            self.configureStartupOnFirstLaunch()
            self.timer = Timer.scheduledTimer(withTimeInterval:60,repeats:true) { [weak self] _ in
                Task { @MainActor in self?.monitorTick() }
            }
            self.loadEvents(then:{self.monitorTick()})
        }) { data in self.readiness=try JSONDecoder().decode(EnvironmentReadiness.self,from:data) }
    }
    func configureStartupOnFirstLaunch() {
        #if !TESTING
        let defaults=UserDefaults.standard
        let wanted=defaults.bool(forKey:"startupWanted")
        if wanted && [.notRegistered,.notFound].contains(SMAppService.mainApp.status) { setStartup(true) }
        else { refreshStartup() }
        #endif
    }
    func refreshStartup() {
        #if !TESTING
        let observed=SMAppService.mainApp.status
        UserDefaults.standard.set(observed.rawValue,forKey:"startupObservedStatus")
        UserDefaults.standard.set(ISO8601DateFormatter().string(from:Date()),forKey:"startupObservedAt")
        UserDefaults.standard.set(Bundle.main.bundleURL.resolvingSymlinksInPath().path,forKey:"startupObservedAppPath")
        UserDefaults.standard.set(Bundle.main.object(forInfoDictionaryKey:"CFBundleVersion"),forKey:"startupObservedBuild")
        switch observed {
        case .enabled:startupEnabled=true;startupStatus="已登記登入後啟動；實際重登／重開機尚未驗證。"
        case .requiresApproval:startupEnabled=false;startupStatus="macOS 要求在系統設定的登入項目允許；尚未啟用。"
        case .notRegistered:startupEnabled=false;startupStatus="登入自啟動未登記。"
        case .notFound:startupEnabled=false;startupStatus="登入項目未找到 App；請保留 App 在固定本機位置後重新登記。"
        @unknown default:startupEnabled=false;startupStatus="登入項目狀態未確認。"
        }
        #endif
    }
    func setStartup(_ enabled:Bool) {
        #if !TESTING
        if enabled {
            let path=Bundle.main.bundleURL.resolvingSymlinksInPath().path
            let userApps=FileManager.default.homeDirectoryForCurrentUser.appendingPathComponent("Applications").path+"/"
            guard path.hasPrefix("/Applications/") || path.hasPrefix(userApps) else {
                startupEnabled=false;startupStatus="此為收納副本，請使用本機版本入口；不登記暫存或 iCloud 位置。";return
            }
        }
        UserDefaults.standard.set(enabled,forKey:"startupWanted")
        if enabled && SMAppService.mainApp.status == .enabled { refreshStartup();return }
        if !enabled && SMAppService.mainApp.status == .notRegistered { refreshStartup();return }
        do {
            if enabled { try SMAppService.mainApp.register() }
            else { try SMAppService.mainApp.unregister() }
            refreshStartup()
        } catch {
            refreshStartup()
            if SMAppService.mainApp.status != .requiresApproval {
                let detail=error as NSError
                startupStatus="登入項目\(enabled ? "登記" : "取消")未完成：\(detail.domain)／\(detail.code)。系統讀回狀態已保留，未宣稱成功。"
            }
        }
        #endif
    }
    func monitorTick() {
        guard autoCheck, !busy, !dialogOpen else { return }
        check(automatic: true)
    }
    private func approveAutomation(_ d: Diagnostic) {
        approvedSources=d.approval_sources.filter{$0.value.enabled}; previousPlan=nil; attemptedPlans.removeAll(); clearChecks=0
        autoRepair=true; autoCheck=true
    }
    func pauseAutomationForRestore() {
        autoRepair=false; previousPlan=nil; clearChecks=0
        automationStatus="恢復時已關閉自動修復，避免下一次監測立即重做；只讀檢查保留。"
    }
    func execute(_ action: String, extra: [String] = [], input: String? = nil, then: (() -> Void)? = nil, finish: @escaping (Data) throws -> Void) {
        guard !busy else { return }
        busy = true; failure = nil; status = "處理中，請保留 App 開啟…"
        mutating = ["repair", "restore"].contains(action)
        if mutating { DoctorDelegate.mutationInProgress = true }
        let selectedHome=configHome
        Task {
            var outcome="returned", eventCode="returned"
            do {
                let data = try await Task.detached(priority: .userInitiated) { try Backend.run(action, extra: extra, input: input,configHome:selectedHome) }.value
                try finish(data)
                if action == "diagnose" && !self.blockedTransactions.isEmpty { eventCode="transaction_blocked" }
                if action == "auto-decision", let object=try? JSONSerialization.jsonObject(with:data) as? [String:Any] {
                    eventCode=object["code"] as? String ?? "returned"
                }
                status = "本次操作已返回；請查看各項證據層次"
            } catch {
                failure = error.localizedDescription; status = "未完成，未宣稱通過"
                if action == "preflight" { readiness=nil;diagnosticIsCurrent=false;previousPlan=nil;clearChecks=0 }
                if action == "runtime-verify" {
                    self.runtimeVerification=RuntimeVerification(state:"failed",phase:"bridge",detail:error.localizedDescription,
                        route:"Codex App Server → node_repl + @oai/sky",generated_at:ISO8601DateFormatter().string(from:Date()),
                        nonce:self.testNonce,clicks:self.testClicks,screenshot:"not_tested")
                }
                outcome="failed"; eventCode="failed"
                if action == "event-history" { self.eventWarning="處理紀錄讀取失敗；未覆蓋原紀錄。" }
                if action == "diagnose" {
                    self.diagnosticIsCurrent=false; self.previousPlan=nil; self.clearChecks=0
                    self.automationStatus="本次檢查失敗；保留舊報告但不可據此修復，下次成功後重新累積穩定觀察。"
                }
                if self.mutating {
                    self.diagnosticIsCurrent=false; self.previousPlan=nil; self.clearChecks=0
                }
                if self.mutating && self.autoRepair { self.autoRepair = false; self.automationStatus = "自動修復已暫停：請核對交易／錯誤，不盲目重試。" }
                self.setDockBadge("!")
            }
            let attempt=OperationAttempt(action:action,outcome:outcome,time:ISO8601DateFormatter().string(from:Date()),error:outcome == "failed" ? failure : nil)
            if action != "event-history" {
                lastAttempt=attempt
                if action == "diagnose" || (action == "preflight" && outcome == "failed") { lastCheckAttempt=attempt }
                if outcome == "failed" { lastFailure=attempt }
                if !["runtime-verify","preflight"].contains(action) { do {
                    let request=try JSONSerialization.data(withJSONObject:["action":action,"code":eventCode])
                    let data=try await Task.detached { try Backend.run("record-event",input:String(decoding:request,as:UTF8.self),configHome:selectedHome) }.value
                    struct Response: Decodable { let events:[EventRow] }
                    self.events=try JSONDecoder().decode(Response.self,from:data).events
                    self.eventWarning=nil
                } catch { self.eventWarning="本機處理紀錄未保存；原有交易保護仍有效，未宣稱紀錄已寫入。" } }
            }
            busy = false
            mutating = false; DoctorDelegate.mutationInProgress = false
            then?()
        }
    }
    func check(automatic: Bool = false) {
        guard !busy else { return }
        if !automatic {
            runtimeVerification=nil;testActive=false;testNonce="尚未啟動";testClicks=0;testResult="待測";testExpression="待測"
        }
        execute("preflight",extra:["--app-path",Bundle.main.bundleURL.path],then:{
            guard self.failure == nil, self.readiness?.config_ready == true else {
                self.diagnosticIsCurrent=false;self.previousPlan=nil;self.clearChecks=0
                self.status="設定環境未就緒；請查看使用準備或選擇正確資料夾，未改另一份設定。"
                if self.failure == nil { self.failure="設定檔未就緒，未使用先前報告修復；請查看使用準備提示。" }
                let attempt=OperationAttempt(action:"preflight",outcome:"failed",time:ISO8601DateFormatter().string(from:Date()),error:self.failure)
                self.lastCheckAttempt=attempt;self.lastFailure=attempt
                return
            }
            self.runCheck(automatic:automatic)
        }) { data in self.readiness=try JSONDecoder().decode(EnvironmentReadiness.self,from:data) }
    }
    func runCheck(automatic:Bool) {
        execute("diagnose", then: {
            if automatic { self.evaluateAutomation() }
            else if self.failure == nil {
                if self.readiness?.runtime_ready == true { self.verifyRuntime() }
                else {
                    self.runtimeVerification=RuntimeVerification(state:"blocked",phase:"preflight",detail:"使用準備尚有缺件；配置檢查已完成，但未啟動操作工具。請處理下列提示後重新檢查。",route:"Codex App Server → node_repl + @oai/sky",generated_at:ISO8601DateFormatter().string(from:Date()),nonce:"not-started",clicks:0,screenshot:"not_tested")
                }
            }
        }) { data in
            self.diagnostic = try JSONDecoder().decode(Diagnostic.self, from: data)
            self.diagnosticIsCurrent=true
            self.rawReport = String(decoding: data, as: UTF8.self)
            self.diagnosticReport=self.rawReport
            self.transactions=self.diagnostic?.transaction_history ?? []
            self.lastCheck = Date().formatted(date: .omitted, time: .standard)
            if let d = self.diagnostic {
                let warnings = (d.plugins + d.mcp + d.network + d.browser).filter { $0.state == "warning" }.count
                let count=warnings+self.blockedTransactions.count
                self.setDockBadge(count > 0 ? String(count) : nil)
                if !self.blockedTransactions.isEmpty {
                    self.autoRepair=false; self.previousPlan=nil
                    self.automationStatus="存在\(self.blockedTransactions.count)筆未完成／不可讀交易；自動修復暫停，請查看備份與恢復。"
                }
            }
        }
    }
    func setAutoRepair(_ value: Bool) {
        if !value { autoRepair = false; automationStatus = "自動修復已關閉；只讀檢查可繼續"; return }
        guard let d = diagnostic, diagnosticIsCurrent, !busy, blockedTransactions.isEmpty else { automationStatus = "先取得有效診斷，並核對未完成交易，再啟用自動修復。"; return }
        dialogOpen = true; defer { dialogOpen = false }
        let alert = NSAlert()
        alert.messageText = "啟用本次 App 執行期間的自動快取修復？"
        let names=d.plugins.filter{$0.enabled == true}.map{$0.name}.joined(separator:"、")
        alert.informativeText = "本次啟用清單：\(names.isEmpty ? "無" : names)。\n固定本次來源版本、指紋及啟用清單；之後新增／停用插件或來源改變會暫停，不默默擴大範圍。\n相同方案須兩次穩定檢查，不改模型、代理、權限，不重啟其他 App。退出後需重新啟用。"
        alert.addButton(withTitle: "啟用自動修復"); alert.addButton(withTitle: "取消")
        guard alert.runModal() == .alertFirstButtonReturn else { return }
        approveAutomation(d)
        automationStatus = "已啟用：等待兩次穩定觀察，不立即改動。"
    }
    func evaluateAutomation() {
        guard autoRepair, autoCheck, !busy, diagnosticIsCurrent, failure == nil, let d = diagnostic else { return }
        if d.repair_count == 0 {
            clearChecks += 1
            if clearChecks >= 2 { attemptedPlans.removeAll() }
        } else { clearChecks = 0 }
        let request = AutoRequest(current: AutoCurrent(d), previous_plan: previousPlan, approved_sources: approvedSources,
                                  attempted_plans: Array(attemptedPlans), cooldown: lastRepairAt.map { Date().timeIntervalSince($0) < 300 } ?? false)
        previousPlan = d.plan_id
        guard let encoded = try? JSONEncoder().encode(request) else { return }
        var decision: AutoDecision?
        execute("auto-decision", input: String(decoding: encoded, as: UTF8.self), then: {
            guard self.autoRepair, self.autoCheck, let decision = decision else { return }
            self.automationStatus = decision.reason
            if decision.pause == true { self.autoRepair=false; return }
            if decision.eligible { self.performAutoRepair(d) }
        }) { data in decision = try JSONDecoder().decode(AutoDecision.self, from: data) }
    }
    func performAutoRepair(_ d: Diagnostic) {
        guard autoRepair, !busy, !attemptedPlans.contains(d.plan_id) else { return }
        attemptedPlans.insert(d.plan_id); lastRepairAt = Date()
        execute("repair", extra: ["--plan", d.plan_id, "--confirmed"], then: { if self.failure == nil { self.check(automatic:true) } }) { data in
            struct Response: Decodable { let repaired: Int; let diagnostic: Diagnostic }
            let response = try JSONDecoder().decode(Response.self, from: data)
            self.mutationReport=String(decoding:data,as:UTF8.self)
            self.diagnosticIsCurrent=false
            self.automationStatus = "自動處理\(response.repaired)項快取；實際工具操作仍未驗證。"
        }
    }
    func classify() {
        let snapshot=input
        execute("classify", input: snapshot) { data in
            let result=try JSONDecoder().decode(Classification.self, from: data)
            if self.input==snapshot { self.classification=result }
        }
    }
    func loadHistory() {
        struct Response: Decodable { let transactions: [Transaction] }
        execute("history") { data in
            self.transactions = try JSONDecoder().decode(Response.self, from: data).transactions
            if !self.blockedTransactions.isEmpty {
                self.autoRepair=false; self.previousPlan=nil
                self.automationStatus="存在未完成／不可讀交易；自動修復暫停，請核對停點。"
            }
        }
    }
    func loadEvents(then: (() -> Void)? = nil) {
        struct Response: Decodable { let events:[EventRow] }
        execute("event-history",then:then) { data in
            self.events=try JSONDecoder().decode(Response.self,from:data).events
            self.eventWarning=nil
        }
    }
    func repair() {
        guard let d = diagnostic, diagnosticIsCurrent, !busy, blockedTransactions.isEmpty else { return }
        if d.repair_count == 0 { check();return }
        dialogOpen = true; defer { dialogOpen = false }
        let names = d.plugins.filter { $0.repairable == true }.map { $0.name }.joined(separator: "、")
        let alert = NSAlert()
        alert.messageText = "確認修復 \(d.repair_count) 項快取／版本連結？"
        alert.informativeText = "項目：\(names)\n先保留交易記錄和必要備份，只替換已確認問題的快取／latest。\n不修改模型、服務等級、代理、安全政策或插件啟用設定。\n請先保存其他任務；App 不會替你退出 ChatGPT。"
        alert.addButton(withTitle: "確認本次修復"); alert.addButton(withTitle: "取消")
        guard alert.runModal() == .alertFirstButtonReturn else { return }
        attemptedPlans.insert(d.plan_id); lastRepairAt=Date(); previousPlan=nil; clearChecks=0
        execute("repair", extra: ["--plan", d.plan_id, "--confirmed"], then: { if self.failure == nil { self.check() } }) { data in
            struct Response: Decodable { let repaired: Int; let diagnostic: Diagnostic }
            let response = try JSONDecoder().decode(Response.self, from: data)
            _=response
            self.mutationReport=String(decoding:data,as:UTF8.self);self.diagnosticIsCurrent=false
        }
    }
    func restore(_ item: Transaction) {
        guard !busy else { return }
        dialogOpen = true; defer { dialogOpen = false }
        let alert = NSAlert()
        alert.messageText = "恢復選定交易？"
        alert.informativeText = "交易：\(item.transaction)\n先核對修復後檔案與备份。內容已變時拒絕覆蓋；新快取保留，不刪除其他資料。"
        alert.addButton(withTitle: "確認恢復"); alert.addButton(withTitle: "取消")
        guard alert.runModal() == .alertFirstButtonReturn else { return }
        pauseAutomationForRestore()
        execute("restore", extra: ["--transaction", item.transaction, "--confirmed"], then: { if self.failure == nil { self.check() } }) { data in
            self.mutationReport = String(decoding: data, as: UTF8.self)
            self.transactions.removeAll(); self.diagnostic = nil; self.diagnosticIsCurrent=false
            self.lastCheck="恢復後待重新檢查"
        }
    }
    func export() {
        guard !busy else { return }
        dialogOpen=true; defer { dialogOpen=false }
        let panel = NSSavePanel()
        panel.allowedContentTypes = [.plainText]; panel.nameFieldStringValue = "Computer-Use-V9-report.txt"
        if panel.runModal() == .OK, let url = panel.url {
            do { try reportText.write(to: url, atomically: true, encoding: .utf8) }
            catch { failure = "報告保存失敗，請確認目的地可寫入。" }
        }
    }
}

struct RowView: View {
    let row: DiagnosticRow
    var label: String {
        switch row.state {
        case "checked":return "本機檢查通過"
        case "configured":return "連接配置已核對"
        case "disabled":return "已確認停用"
        case "warning":return "需處理"
        default:return "仍需核對"
        }
    }
    var color: Color { ["checked","configured"].contains(row.state) ? .cyan : row.state == "warning" ? .orange : .secondary }
    var body: some View {
        VStack(alignment: .leading, spacing: 9) {
            HStack { Text(row.name).font(.headline); Spacer(); Text(label).font(.caption).foregroundStyle(color) }
            if let version = row.version { Text("來源版本：\(version)").font(.caption).foregroundStyle(.secondary) }
            Text(row.detail).font(.subheadline).foregroundStyle(.secondary).fixedSize(horizontal: false, vertical: true)
        }.padding(16).frame(maxWidth: .infinity, alignment: .leading)
            .background(.quaternary.opacity(0.4), in: RoundedRectangle(cornerRadius: 14))
    }
}

struct ContentView: View {
    @ObservedObject private var model = Model.shared
    var body: some View {
        NavigationSplitView {
            VStack(alignment: .leading, spacing: 18) {
                Label("Computer Use", systemImage: "desktopcomputer").font(.title3).padding(.top, 18)
                Text("DOCTOR · V9").font(.caption.monospaced()).foregroundStyle(.secondary)
                List(Section.allCases, selection: $model.section) { item in Label(item.rawValue, systemImage: item.icon).tag(item) }
                Text("本機診斷與定向修復\n不繞過授權或平台限制").font(.caption).foregroundStyle(.secondary).padding(.bottom, 14)
            }.padding(.horizontal, 12).navigationSplitViewColumnWidth(min: 210, ideal: 230)
        } detail: {
            VStack(alignment: .leading, spacing: 18) {
                HStack {
                    VStack(alignment: .leading, spacing: 6) {
                        Text((model.section ?? .overview).rawValue).font(.largeTitle.weight(.semibold))
                        Text(model.status).font(.subheadline).foregroundStyle(.secondary)
                    }
                    Spacer()
                    if model.busy { ProgressView().controlSize(.small) }
                    Button("開始檢查") { model.check() }.buttonStyle(.borderedProminent).disabled(model.busy)
                }
                if let message = model.failure {
                    Label(message, systemImage: "exclamationmark.triangle").foregroundStyle(.orange).textSelection(.enabled)
                }
                if let warning=model.eventWarning { Text(warning).foregroundStyle(.orange) }
                if !model.blockedTransactions.isEmpty {
                    Label("尚有\(model.blockedTransactions.count)筆未完成／不可讀交易，不能只以快取正常判定已處理完畢。",systemImage:"exclamationmark.shield").foregroundStyle(.orange)
                }
                if model.diagnostic != nil && !model.diagnosticIsCurrent {
                    Text("下方是先前報告，本次檢查未成功；已禁止據此修復。").foregroundStyle(.orange)
                }
                VStack(alignment: .leading, spacing: 6) {
                    Text("使用準備與設定位置").font(.headline)
                    Text(model.configLocationText)
                        .font(.caption).textSelection(.enabled)
                        .accessibilityElement(children:.ignore).accessibilityLabel(model.configLocationText)
                        .accessibilityIdentifier("doctor-config-location").id(model.configLocationText)
                    HStack {
                        Button("選擇設定資料夾") { model.chooseConfigFolder() }.disabled(model.busy)
                        if model.configHome != nil { Button("使用環境／預設位置") { model.useDefaultConfigFolder() }.disabled(model.busy) }
                    }
                    DisclosureGroup("或直接指定設定路徑") {
                        HStack {
                            TextField("自己的 Codex 設定資料夾絕對路徑",text:$model.configPathInput)
                            Button("使用此路徑") { model.applyConfigPath() }.disabled(model.busy)
                        }
                    }
                    if let readiness=model.readiness, !readiness.runtime_ready {
                        DisclosureGroup("實測尚未就緒：查看缺件與處理方法") {
                            ScrollView {
                                VStack(alignment:.leading,spacing:6) {
                                    ForEach(readiness.rows.filter { $0.state != "checked" }) { row in
                                        Text(row.name+"："+row.detail).font(.caption).foregroundStyle(.orange).fixedSize(horizontal:false,vertical:true)
                                    }
                                }
                            }.frame(maxHeight:160)
                        }
                    }
                    Text("缺件不自動安裝。自動檢查只讀；人工實測可能初始化既有工具服務，請只使用你信任的設定。").font(.caption).foregroundStyle(.secondary)
                    HStack {
                        Toggle("自動檢查（60秒）", isOn: $model.autoCheck)
                        Toggle("自動修復已確認問題", isOn: Binding(get: { model.autoRepair }, set: { model.setAutoRepair($0) })).disabled(model.busy)
                        Spacer(); Text("上次：\(model.lastCheck)").font(.caption).foregroundStyle(.secondary)
                    }.toggleStyle(.switch)
                    Text(model.automationStatus).font(.caption).foregroundStyle(.secondary)
                    HStack {
                        Toggle("登入 Mac 後啟動",isOn:Binding(get:{model.startupEnabled},set:{model.setStartup($0)}))
                            .disabled(model.busy || model.installedVersionAvailable)
                        Text(model.startupStatus).font(.caption).foregroundStyle(.secondary)
                    }.toggleStyle(.switch)
                    Text(model.instanceStatus).font(.caption).foregroundStyle(.secondary)
                    if model.installedVersionAvailable { Button("開啟已核對的本機版本") { model.openInstalledVersion() } }
                }
                VStack(alignment:.leading,spacing:6) {
                    Text("原生操作實測：\(model.runtimeTitle)").font(.headline)
                    Text(model.runtimeVerification?.detail ?? "手動檢查／修復會讀取本視窗，實際點擊測試鍵並回讀本次結果；背景檢查不搶焦點。")
                        .font(.caption).foregroundStyle(.secondary)
                    Text("透過官方已認證的工具上下文實測；不借用會話憑證，不發起模型推理。Doctor 直接 API 權限列於診斷報告，並非此路徑的通過證明。").font(.caption).foregroundStyle(.secondary)
                    HStack {
                        ForEach(["清除","1","加號","等號"],id:\.self) { key in
                            Button("實測：\(key)") { model.testPress(key) }.disabled(!model.testActive)
                        }
                    }
                    Text(model.testStateText).font(.caption.monospaced())
                        .accessibilityElement(children:.ignore).accessibilityLabel(model.testStateText)
                        .accessibilityIdentifier("doctor-test-state").id(model.testStateText)
                }.padding(10).background(.quaternary,in:RoundedRectangle(cornerRadius:10))
                ScrollView {
                    VStack(alignment: .leading, spacing: 14) {
                        switch model.section ?? .overview {
                        case .overview:
                            Text("先查明原因，再處理需要修的部分。").font(.title2)
                            Text("檢查不修改配置。快取正常、工具連接和實際 App 操作是不同的驗收層次。這個 App 不能直接授權 Jarvis 或控制所有會話。")
                                .foregroundStyle(.secondary).fixedSize(horizontal: false, vertical: true)
                            if let d = model.diagnostic {
                                HStack(spacing: 16) {
                                    metric("插件", "\(d.plugins.count)")
                                    metric("可修復項", "\(d.repair_count)")
                                    metric("待核對交易", "\(model.blockedTransactions.count)")
                                    metric("運行驗收", model.runtimeTitle)
                                }
                                Text("插件來源、快取與版本連結").font(.title2)
                                ForEach(d.plugins) { RowView(row: $0) }
                                repairButton
                            } else {
                                Label("點擊右上角開始檢查", systemImage: "magnifyingglass").padding(.vertical, 30)
                            }
                            if let d = model.diagnostic {
                                Text("工具配置（不啟動任意配置命令）").font(.title2).padding(.top, 10)
                                if d.mcp.isEmpty { Text("未讀到獨立工具配置；可能由插件動態提供，不能判定缺工具。") }
                                ForEach(d.mcp) { RowView(row: $0) }
                            }
                            Text("瀏覽器原生連接").font(.title2)
                            Text("只核對本機連接描述與檔案；系統代理／VPN 檢查已移除。").foregroundStyle(.secondary)
                            if let d = model.diagnostic { ForEach(d.browser) { RowView(row:$0) } }
                            Text("貼入錯誤或交接記錄，在本機分析").font(.title2)
                            Text("請先移除密碼、令牌和無關私人資料。輸入不會送到外部服務，也不會自動保存。分類只是線索，不是根因確認。").foregroundStyle(.secondary)
                            TextEditor(text: $model.input).font(.body.monospaced()).frame(minHeight: 180).padding(8).background(.quaternary, in: RoundedRectangle(cornerRadius: 12))
                            Button("分析記錄", action: model.classify).disabled(model.busy || model.input.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty)
                            if let c = model.classification {
                                if c.matches.isEmpty { Text("沒有匹配已知類型，不能判定故障原因。") }
                                ForEach(c.matches) { item in
                                    VStack(alignment: .leading, spacing: 8) { Text(item.title).font(.headline); Text(item.next_step).foregroundStyle(.secondary) }.padding(14)
                                }
                                Text(c.boundary).font(.caption).foregroundStyle(.secondary)
                            }
                        case .backups:
                            HStack { Text("修復交易與備份").font(.title2); Spacer(); Button("讀取記錄", action: model.loadHistory).disabled(model.busy) }
                            Text("未完成交易只顯示停點，不重做。恢復前核對修復後內容，拒絕覆蓋後來的改動。").foregroundStyle(.secondary)
                            if model.transactions.isEmpty { Text("尚未讀取記錄，或沒有本 App 的修復交易。") }
                            ForEach(model.transactions) { item in
                                VStack(alignment: .leading, spacing: 8) {
                                    Text(item.transaction).font(.caption.monospaced()).textSelection(.enabled)
                                    Text("狀態：\(item.status) · \(item.count) 項").font(.subheadline)
                                    ForEach(item.steps, id: \.self) { Text($0).font(.caption.monospaced()).foregroundStyle(.secondary) }
                                    if item.status == "cache_repaired" { Button("恢復這次修復") { model.restore(item) }.disabled(model.busy) }
                                    else if item.status != "restored" && item.status != "no_changes" { Text("需核對交易停點與備份，不自動繼續。").foregroundStyle(.orange) }
                                }.padding(14).frame(maxWidth: .infinity, alignment: .leading).background(.quaternary.opacity(0.4), in: RoundedRectangle(cornerRadius: 12))
                            }
                        case .events:
                            HStack { Text("本機處理紀錄").font(.title2); Spacer(); Button("重新讀取") { model.loadEvents() }.disabled(model.busy) }
                            Text("只保留最近200筆時間、動作與結果代碼；不保存貼入原文、憑證或原始配置。交易備份不受此筆數限制。").foregroundStyle(.secondary)
                            ForEach(model.events.reversed()) { event in
                                Text("\(event.created_at) · \(event.title)").font(.caption).textSelection(.enabled)
                            }
                        case .report:
                            HStack { Button("匯出報告", action: model.export).disabled(model.busy); Button("複製報告") { NSPasteboard.general.clearContents(); NSPasteboard.general.setString(model.reportText, forType: .string) } }
                            Text(model.reportText).font(.caption.monospaced()).textSelection(.enabled).frame(maxWidth: .infinity, alignment: .leading)
                        }
                    }.frame(maxWidth: .infinity, alignment: .leading)
                }
                Text("V9 · App 開啟時監測 · 不修改服務等級、模型或安全政策").font(.caption).foregroundStyle(.secondary)
            }.padding(28).frame(minWidth: 620, minHeight: 560)
        }.frame(minWidth: 880, minHeight: 640).onAppear { model.startMonitoring() }
    }
    var repairButton: some View {
        Button("修復並核查全部項目", action: model.repair).buttonStyle(.bordered)
            .disabled(model.busy || !model.diagnosticIsCurrent || !model.blockedTransactions.isEmpty)
    }
    func metric(_ name: String, _ value: String) -> some View {
        VStack(alignment: .leading, spacing: 8) { Text(name).font(.caption).foregroundStyle(.secondary); Text(value).font(.title2.weight(.medium)) }
            .padding(16).frame(maxWidth: .infinity, alignment: .leading).background(.quaternary.opacity(0.4), in: RoundedRectangle(cornerRadius: 14))
    }
}

final class DoctorDelegate: NSObject, NSApplicationDelegate {
    static var mutationInProgress = false
    func applicationShouldTerminate(_ sender: NSApplication) -> NSApplication.TerminateReply {
        if Self.mutationInProgress {
            let alert=NSAlert(); alert.messageText="正在修復／恢復，請等交易返回後再退出。"
            alert.informativeText="不強制中斷寫入；未完成狀態會保留供核對。";alert.runModal()
            return .terminateCancel
        }
        return .terminateNow
    }
}
#if !TESTING
struct DoctorMenuView: View {
    @ObservedObject private var model=Model.shared
    @Environment(\.openWindow) private var openWindow
    var body: some View {
        Text(model.busy ? "正在處理" : model.autoCheck ? "自動檢查已開啟" : "自動檢查已暫停")
        Text("待核對交易：\(model.blockedTransactions.count)")
        Text(model.automationStatus)
        Button("顯示主視窗") { openWindow(id:"doctor"); NSApplication.shared.activate(ignoringOtherApps:true) }
        Button("立即檢查") { model.check() }.disabled(model.busy)
        Button("暫停自動檢查") { model.autoCheck=false }.disabled(!model.autoCheck)
        Button("恢復自動檢查") { model.autoCheck=true; model.monitorTick() }.disabled(model.autoCheck)
        Button("關閉自動修復") { model.setAutoRepair(false) }.disabled(!model.autoRepair)
        Divider()
        Button("退出 App") { NSApplication.shared.terminate(nil) }
    }
}
@main struct DoctorApp: App {
    @NSApplicationDelegateAdaptor(DoctorDelegate.self) var delegate
    var body: some Scene {
        WindowGroup("Computer Use Doctor V9 Preview", id:"doctor") { ContentView().preferredColorScheme(.dark) }
            .defaultSize(width: 1020, height: 750)
        MenuBarExtra("Computer Use Doctor",systemImage:"stethoscope") { DoctorMenuView() }
    }
}
#endif
