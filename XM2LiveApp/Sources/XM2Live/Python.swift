import Foundation

/// Python qui fait les conversions. xm2live.py a besoin de numpy et de lxml : l'app le vérifie au
/// lancement pour dire clairement ce qui manque, plutôt qu'un traceback à la première conversion.
enum PythonStatus: Equatable {
    case checking
    case ready(path: String)
    case missingModules(path: String, modules: [String])
    case notFound

    static let requiredModules = ["numpy", "lxml"]

    /// python3 essayés, dans l'ordre : Homebrew (Apple silicon, puis Intel ou python.org), puis celui
    /// des outils de développement d'Apple. /usr/bin/python3 n'est qu'un relais vers ce dernier :
    /// sans les outils, il ouvre la fenêtre de leur installation, d'où le passage par xcode-select.
    static func candidates() -> [String] {
        var paths = ["/opt/homebrew/bin/python3", "/usr/local/bin/python3"]
        if let developer = run("/usr/bin/xcode-select", ["-p"]), developer.status == 0 {
            let dir = developer.output.trimmingCharacters(in: .whitespacesAndNewlines)
            paths.append(dir + "/usr/bin/python3")
        }
        return paths.filter { FileManager.default.isExecutableFile(atPath: $0) }
    }

    /// Le premier python3 qui importe les modules requis ; sinon le premier trouvé, avec ce qui lui
    /// manque. Lent (import de numpy) : à appeler hors du thread principal.
    static func detect() -> PythonStatus {
        let probe = """
            missing = []
            for name in ('numpy', 'lxml.etree'):
                try:
                    __import__(name)
                except Exception:
                    missing.append(name.split('.')[0])
            print(' '.join(missing))
            """
        var firstFound: PythonStatus?
        for path in candidates() {
            guard let result = run(path, ["-c", probe]), result.status == 0 else { continue }
            let missing = result.output.split(whereSeparator: \.isWhitespace).map(String.init)
            if missing.isEmpty { return .ready(path: path) }
            if firstFound == nil { firstFound = .missingModules(path: path, modules: missing) }
        }
        return firstFound ?? .notFound
    }

    /// Explication affichée quand Python n'est pas prêt, et commande qui règle le problème.
    var problem: (message: String, command: String)? {
        switch self {
        case .checking, .ready:
            return nil
        case .missingModules(let path, let modules):
            return ("\(path) n'a pas les modules \(modules.joined(separator: " et ")), nécessaires à la "
                    + "conversion. Installez-les dans le Terminal, puis cliquez sur Vérifier :",
                    "\(path) -m pip install \(modules.joined(separator: " "))")
        case .notFound:
            return ("Python 3 introuvable (cherché dans /opt/homebrew/bin, /usr/local/bin et les outils de "
                    + "développement d'Apple). Installez Python 3 (python.org ou Homebrew), puis les modules "
                    + "numpy et lxml dans le Terminal, et cliquez sur Vérifier :",
                    "python3 -m pip install \(Self.requiredModules.joined(separator: " "))")
        }
    }

    /// Lance un programme et attend sa fin : code de sortie et sortie standard, nil s'il ne démarre pas.
    private static func run(_ executable: String, _ arguments: [String]) -> (status: Int32, output: String)? {
        let process = Process()
        process.executableURL = URL(fileURLWithPath: executable)
        process.arguments = arguments
        let pipe = Pipe()
        process.standardOutput = pipe
        process.standardError = FileHandle.nullDevice
        do {
            try process.run()
        } catch {
            return nil
        }
        let data = pipe.fileHandleForReading.readDataToEndOfFile()
        process.waitUntilExit()
        return (process.terminationStatus, String(decoding: data, as: UTF8.self))
    }
}
