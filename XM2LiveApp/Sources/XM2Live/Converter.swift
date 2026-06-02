import Foundation
import Combine

/// Options de conversion exposées dans l'interface, correspondant aux flags CLI de xm2live.py.
struct ConversionOptions {
    var panAutomation = true
    var sampleOffset = true
    var envelope = false
    var mergeTracks = false
    /// Dossier de sortie racine choisi par l'utilisateur. nil = "à côté du fichier source".
    var outputRoot: URL? = nil
}

@MainActor
final class Converter: ObservableObject {
    @Published var log: String = ""
    @Published var isRunning = false
    @Published var progressText = ""
    /// Dossiers des projets Ableton effectivement produits lors de la dernière conversion.
    @Published var outputDirs: [URL] = []

    private var task: Task<Void, Never>?

    static let supportedExtensions: Set<String> = ["xm", "mod"]

    // MARK: - Localisation de Python et des scripts

    /// Retourne le premier python3 trouvé parmi les emplacements habituels.
    static func findPython() -> String? {
        let candidates = [
            "/opt/homebrew/bin/python3",
            "/usr/local/bin/python3",
            "/usr/bin/python3"
        ]
        return candidates.first { FileManager.default.isExecutableFile(atPath: $0) }
    }

    /// Répertoire contenant xm2live.py : ressources embarquées en priorité,
    /// sinon repli sur le projet à /Users/sam/xm2live_v2.
    static func scriptsDirectory() -> URL {
        let fm = FileManager.default
        if let res = Bundle.main.resourceURL {
            let bundled = res.appendingPathComponent("xm2live", isDirectory: true)
            if fm.fileExists(atPath: bundled.appendingPathComponent("xm2live.py").path) {
                return bundled
            }
        }
        return URL(fileURLWithPath: "/Users/sam/xm2live_v2", isDirectory: true)
    }

    // MARK: - Découverte des fichiers

    /// Développe une liste d'entrées (fichiers ou dossiers) en fichiers .xm/.mod.
    static func expand(urls: [URL]) -> [URL] {
        let fm = FileManager.default
        var files: [URL] = []
        for url in urls {
            var isDir: ObjCBool = false
            guard fm.fileExists(atPath: url.path, isDirectory: &isDir) else { continue }
            if isDir.boolValue {
                if let en = fm.enumerator(at: url, includingPropertiesForKeys: nil) {
                    for case let f as URL in en
                    where supportedExtensions.contains(f.pathExtension.lowercased()) {
                        files.append(f)
                    }
                }
            } else if supportedExtensions.contains(url.pathExtension.lowercased()) {
                files.append(url)
            }
        }
        // Dédoublonnage en conservant l'ordre.
        var seen = Set<String>()
        return files.filter { seen.insert($0.standardizedFileURL.path).inserted }
                    .sorted { $0.lastPathComponent.localizedStandardCompare($1.lastPathComponent) == .orderedAscending }
    }

    // MARK: - Conversion

    func cancel() {
        task?.cancel()
    }

    func run(inputs: [URL], options: ConversionOptions) {
        guard !isRunning else { return }
        let files = Converter.expand(urls: inputs)
        guard !files.isEmpty else {
            appendLine("⚠️  Aucun fichier .xm ou .mod trouvé dans la sélection.")
            return
        }
        guard let python = Converter.findPython() else {
            appendLine("❌ python3 introuvable (cherché dans /opt/homebrew, /usr/local, /usr).")
            return
        }
        let scriptsDir = Converter.scriptsDirectory()
        let script = scriptsDir.appendingPathComponent("xm2live.py")
        guard FileManager.default.fileExists(atPath: script.path) else {
            appendLine("❌ Script introuvable: \(script.path)")
            return
        }

        log = ""
        outputDirs = []
        isRunning = true
        task = Task { [weak self] in
            guard let self else { return }
            var ok = 0, fail = 0
            var produced: [URL] = []
            for (i, file) in files.enumerated() {
                if Task.isCancelled { break }
                self.setProgress("Conversion \(i + 1)/\(files.count) — \(file.lastPathComponent)")
                self.appendLine("\n" + String(repeating: "=", count: 60))
                self.appendLine("[\(i + 1)/\(files.count)] \(file.lastPathComponent)")
                self.appendLine(String(repeating: "=", count: 60))

                let args = self.buildArguments(script: script, file: file, options: options)
                let code = await self.launch(python: python, args: args, workingDir: scriptsDir)
                if code == 0 {
                    ok += 1
                    produced.append(self.outputProjectDir(for: file, options: options))
                } else {
                    fail += 1
                }
            }
            // Ne conserve que les dossiers réellement présents sur le disque.
            let fm = FileManager.default
            self.outputDirs = produced.filter { fm.fileExists(atPath: $0.path) }
            self.appendLine("\n" + String(repeating: "=", count: 60))
            if Task.isCancelled {
                self.appendLine("⏸️  Interrompu — \(ok) réussite(s), \(fail) échec(s).")
            } else {
                self.appendLine("✅ Terminé — \(ok) réussite(s), \(fail) échec(s) sur \(files.count) fichier(s).")
            }
            self.isRunning = false
            self.progressText = ""
        }
    }

    /// Dossier du projet Ableton produit pour un fichier donné, en reproduisant
    /// le nommage du script. Sert au flag --output (cas personnalisé) et au
    /// repérage du dossier de destination à ouvrir après conversion.
    func outputProjectDir(for file: URL, options: ConversionOptions) -> URL {
        let name = file.deletingPathExtension().lastPathComponent
        let projectName = "\(name)_Ableton_Project"
        if let root = options.outputRoot {
            return root.appendingPathComponent(projectName, isDirectory: true)
        }
        // Défaut du script : <dossier source>/Conversions Ableton Live/<nom>_Ableton_Project
        return file.deletingLastPathComponent()
            .appendingPathComponent("Conversions Ableton Live", isDirectory: true)
            .appendingPathComponent(projectName, isDirectory: true)
    }

    private func buildArguments(script: URL, file: URL, options: ConversionOptions) -> [String] {
        var args = [script.path, file.path]
        if options.panAutomation { args.append("--pan-automation") }
        if options.sampleOffset { args.append("--sample-offset") }
        if options.envelope { args.append("--envelope") }
        if options.mergeTracks { args.append("--merge-tracks") }
        if options.outputRoot != nil {
            // Cas personnalisé : on passe explicitement le dossier au script.
            args.append("--output")
            args.append(outputProjectDir(for: file, options: options).path)
        }
        return args
    }

    /// Lance le process et streame stdout+stderr dans le log. Retourne le code de sortie.
    private func launch(python: String, args: [String], workingDir: URL) async -> Int32 {
        await withCheckedContinuation { (continuation: CheckedContinuation<Int32, Never>) in
            let process = Process()
            process.executableURL = URL(fileURLWithPath: python)
            process.arguments = args
            process.currentDirectoryURL = workingDir
            // Force UTF-8 et sortie non bufferisée côté Python pour un affichage temps réel.
            var env = ProcessInfo.processInfo.environment
            env["PYTHONUNBUFFERED"] = "1"
            env["PYTHONIOENCODING"] = "utf-8"
            process.environment = env

            let pipe = Pipe()
            process.standardOutput = pipe
            process.standardError = pipe

            pipe.fileHandleForReading.readabilityHandler = { handle in
                let data = handle.availableData
                guard !data.isEmpty, let text = String(data: data, encoding: .utf8) else { return }
                Task { @MainActor [weak self] in self?.append(text) }
            }

            process.terminationHandler = { proc in
                pipe.fileHandleForReading.readabilityHandler = nil
                // Vide le reste du tampon.
                let rest = pipe.fileHandleForReading.readDataToEndOfFile()
                if !rest.isEmpty, let text = String(data: rest, encoding: .utf8) {
                    Task { @MainActor [weak self] in self?.append(text) }
                }
                continuation.resume(returning: proc.terminationStatus)
            }

            // Si la tâche Swift est annulée, on tue le process.
            Task { [weak self] in
                while process.isRunning {
                    if Task.isCancelled { process.terminate(); break }
                    try? await Task.sleep(nanoseconds: 200_000_000)
                }
                _ = self
            }

            do {
                try process.run()
            } catch {
                Task { @MainActor [weak self] in self?.appendLine("❌ Échec du lancement: \(error.localizedDescription)") }
                continuation.resume(returning: -1)
            }
        }
    }

    // MARK: - Helpers log (toujours sur le main actor)

    private func append(_ text: String) {
        log += text
    }

    private func appendLine(_ text: String) {
        log += text + "\n"
    }

    private func setProgress(_ text: String) {
        progressText = text
    }
}
