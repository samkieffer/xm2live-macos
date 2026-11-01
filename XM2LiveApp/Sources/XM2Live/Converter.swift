import Foundation
import Combine

/// Résultat de la dernière conversion d'un fichier, affiché sur sa ligne.
enum FileStatus {
    case ok          // set écrit et valide
    case invalid     // set écrit, mais le validateur y trouve des erreurs (code de sortie 3)
    case failed      // la conversion a échoué
    case skipped     // le projet existait déjà, laissé tel quel
}

@MainActor
final class Converter: ObservableObject {
    @Published var log: String = ""
    @Published var isRunning = false
    @Published var progressText = ""
    /// Dossiers des projets Ableton effectivement produits lors de la dernière conversion.
    @Published var outputDirs: [URL] = []
    /// Python utilisé pour les conversions, vérifié au lancement (checkPython).
    @Published var python: PythonStatus = .checking
    /// Résultat de la dernière conversion, par chemin de fichier (standardizedFileURL.path).
    @Published var statuses: [String: FileStatus] = [:]
    /// Fichier en cours de conversion (même clé que `statuses`).
    @Published var currentFile: String?

    private var task: Task<Void, Never>?
    /// Process Python en cours : Annuler l'arrête (SIGTERM, xm2live.py sort proprement).
    private var currentProcess: Process?

    static let supportedExtensions: Set<String> = ["xm", "mod"]
    /// Code de sortie de xm2live.py quand le set est écrit avec des erreurs de validation (EXIT_INVALID_SET).
    static let invalidSetExitCode: Int32 = 3

    // MARK: - Localisation de Python et des scripts

    func checkPython() async {
        python = .checking
        python = await Task.detached { PythonStatus.detect() }.value
    }

    /// Répertoire contenant xm2live.py : ressources embarquées en priorité,
    /// sinon repli sur le dossier du projet (utile en mode `swift run` dev).
    static func scriptsDirectory() -> URL {
        let fm = FileManager.default
        if let res = Bundle.main.resourceURL {
            let bundled = res.appendingPathComponent("xm2live", isDirectory: true)
            if fm.fileExists(atPath: bundled.appendingPathComponent("xm2live.py").path) {
                return bundled
            }
        }
        return URL(fileURLWithPath: "/Users/sam/Claude projets/XM2Live", isDirectory: true)
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

    /// Fichiers à convertir : chaque entrée développée en fichiers, avec ses options. Déduplique
    /// par chemin (premier gagne) puis trie par nom de fichier.
    static func plan(items: [InputItem]) -> [(url: URL, options: TrackOptions)] {
        var seen = Set<String>()
        var files: [(url: URL, options: TrackOptions)] = []
        for item in items {
            for file in expand(urls: [item.url]) where seen.insert(file.standardizedFileURL.path).inserted {
                files.append((file, item.options))
            }
        }
        return files.sorted { $0.url.lastPathComponent.localizedStandardCompare($1.url.lastPathComponent) == .orderedAscending }
    }

    // MARK: - Conversion

    func cancel() {
        task?.cancel()
        if let process = currentProcess, process.isRunning {
            process.terminate()
        }
    }

    /// Convertit `files` ; ceux de `skipping` (projets existants à garder) sont laissés tels quels.
    func run(files: [(url: URL, options: TrackOptions)], outputRoot: URL?, skipping: Set<URL> = []) {
        guard !isRunning else { return }
        guard !files.isEmpty else {
            appendLine("⚠️  Aucun fichier .xm ou .mod trouvé dans la sélection.")
            return
        }
        guard case .ready(let python) = python else {
            appendLine("❌ Python n'est pas prêt : voir le message en haut de la fenêtre.")
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
        statuses = [:]
        isRunning = true
        appendLine("Python : \(python)")
        task = Task { [weak self] in
            guard let self else { return }
            var produced: [URL] = []
            for (i, entry) in files.enumerated() {
                if Task.isCancelled { break }
                let file = entry.url
                let key = file.standardizedFileURL.path
                if skipping.contains(file) {
                    self.statuses[key] = .skipped
                    self.appendLine("⏭️  \(file.lastPathComponent) : projet existant, gardé tel quel")
                    continue
                }
                self.currentFile = key
                self.setProgress("Conversion \(i + 1)/\(files.count) — \(file.lastPathComponent)")
                self.appendLine("\n" + String(repeating: "=", count: 60))
                self.appendLine("[\(i + 1)/\(files.count)] \(file.lastPathComponent)")
                self.appendLine(String(repeating: "=", count: 60))

                let args = self.buildArguments(script: script, file: file, options: entry.options, outputRoot: outputRoot)
                let code = await self.launch(python: python, args: args, workingDir: scriptsDir)
                if Task.isCancelled { break }  // interrompu en cours de route : ni réussite ni échec
                switch code {
                case 0:
                    self.statuses[key] = .ok
                case Converter.invalidSetExitCode:
                    self.statuses[key] = .invalid
                default:
                    self.statuses[key] = .failed
                }
                if code == 0 || code == Converter.invalidSetExitCode {
                    produced.append(self.outputProjectDir(for: file, outputRoot: outputRoot))
                }
            }
            // Ne conserve que les dossiers réellement présents sur le disque.
            let fm = FileManager.default
            self.outputDirs = produced.filter { fm.fileExists(atPath: $0.path) }
            self.currentFile = nil
            let counts = Dictionary(grouping: self.statuses.values, by: { $0 }).mapValues(\.count)
            var summary = "\(counts[.ok] ?? 0) réussite(s)"
            if let invalid = counts[.invalid] { summary += ", \(invalid) avec erreurs de validation" }
            summary += ", \(counts[.failed] ?? 0) échec(s)"
            if let skipped = counts[.skipped] { summary += ", \(skipped) gardé(s) tel(s) quel(s)" }
            self.appendLine("\n" + String(repeating: "=", count: 60))
            if Task.isCancelled {
                self.appendLine("⏸️  Interrompu — \(summary).")
            } else {
                self.appendLine("✅ Terminé — \(summary) sur \(files.count) fichier(s).")
            }
            self.isRunning = false
            self.progressText = ""
        }
    }

    /// Dossier du projet Ableton produit pour un fichier donné, en reproduisant
    /// le nommage du script. Sert au flag --output (cas personnalisé) et au
    /// repérage du dossier de destination à ouvrir après conversion.
    func outputProjectDir(for file: URL, outputRoot: URL?) -> URL {
        let name = file.deletingPathExtension().lastPathComponent
        let projectName = "\(name)_Ableton_Project"
        if let root = outputRoot {
            return root.appendingPathComponent(projectName, isDirectory: true)
        }
        // Défaut du script : <dossier source>/Conversions Ableton Live/<nom>_Ableton_Project
        return file.deletingLastPathComponent()
            .appendingPathComponent("Conversions Ableton Live", isDirectory: true)
            .appendingPathComponent(projectName, isDirectory: true)
    }

    /// Set Live que la conversion de `file` écrit (et remplace s'il existe) : <projet>/<nom>.als
    func projectFile(for file: URL, outputRoot: URL?) -> URL {
        outputProjectDir(for: file, outputRoot: outputRoot)
            .appendingPathComponent(file.deletingPathExtension().lastPathComponent + ".als")
    }

    private func buildArguments(script: URL, file: URL, options: TrackOptions, outputRoot: URL?) -> [String] {
        var args = [script.path, file.path]
        if options.panAutomation { args.append("--pan-automation") }
        if options.sampleOffset { args.append("--sample-offset") }
        if options.envelope { args.append("--envelope") }
        if options.pitchEffects { args.append("--pitch-effects") }
        if options.mergeTracks { args.append("--merge-tracks") }
        if outputRoot != nil {
            // Cas personnalisé : on passe explicitement le dossier au script.
            args.append("--output")
            args.append(outputProjectDir(for: file, outputRoot: outputRoot).path)
        }
        return args
    }

    /// Lance le process et streame stdout+stderr dans le log. Retourne le code de sortie.
    private func launch(python: String, args: [String], workingDir: URL) async -> Int32 {
        let code = await withCheckedContinuation { (continuation: CheckedContinuation<Int32, Never>) in
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

            do {
                try process.run()
                currentProcess = process
            } catch {
                appendLine("❌ Échec du lancement: \(error.localizedDescription)")
                continuation.resume(returning: -1)
            }
        }
        currentProcess = nil
        return code
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
