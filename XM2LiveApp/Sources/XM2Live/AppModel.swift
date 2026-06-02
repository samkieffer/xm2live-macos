import SwiftUI
import AppKit

/// État partagé : liste des entrées (fichiers/dossiers) à convertir.
/// Permet au délégué d'app (fichiers déposés sur l'icône du Dock) et à l'UI
/// d'alimenter la même source.
@MainActor
final class AppModel: ObservableObject {
    static let shared = AppModel()
    @Published var inputs: [URL] = []

    func add(_ urls: [URL]) {
        inputs.append(contentsOf: urls)
    }

    func set(_ urls: [URL]) {
        inputs = urls
    }

    func remove(_ url: URL) {
        inputs.removeAll { $0 == url }
    }

    func clear() {
        inputs = []
    }
}

/// Reçoit les fichiers ouverts via le Finder ou déposés sur l'icône du Dock.
final class AppDelegate: NSObject, NSApplicationDelegate {
    func application(_ application: NSApplication, open urls: [URL]) {
        Task { @MainActor in AppModel.shared.add(urls) }
    }
}
