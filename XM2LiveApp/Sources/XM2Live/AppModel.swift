import SwiftUI
import AppKit

/// Options de conversion d'un morceau, correspondant aux flags CLI de xm2live.py.
/// Réglables globalement (tous les morceaux) ou individuellement par ligne.
struct TrackOptions: Equatable {
    var panAutomation = true
    var sampleOffset = true
    var envelope = true
    var mergeTracks = false
}

/// Une entrée de la file de conversion : un fichier ou un dossier, avec ses
/// propres options. Pour un dossier, les options s'appliquent à tous ses fichiers.
struct InputItem: Identifiable, Equatable {
    let url: URL
    var options: TrackOptions
    var id: URL { url }
}

/// État partagé : liste des entrées (fichiers/dossiers) à convertir.
/// Permet au délégué d'app (fichiers déposés sur l'icône du Dock) et à l'UI
/// d'alimenter la même source.
@MainActor
final class AppModel: ObservableObject {
    static let shared = AppModel()
    @Published var items: [InputItem] = []

    /// Options appliquées aux nouveaux fichiers ajoutés (drop, sélecteur, Dock),
    /// pour qu'ils héritent du réglage global courant.
    var defaultOptions = TrackOptions()

    // MARK: - Mutation de la file

    func add(_ urls: [URL]) {
        let existing = Set(items.map(\.url))
        let newItems = urls
            .filter { !existing.contains($0) }
            .map { InputItem(url: $0, options: defaultOptions) }
        items.append(contentsOf: newItems)
    }

    func set(_ urls: [URL]) {
        items = urls.map { InputItem(url: $0, options: defaultOptions) }
    }

    func remove(_ url: URL) {
        items.removeAll { $0.url == url }
    }

    func clear() {
        items = []
    }

    // MARK: - Options par ligne et globales

    /// Modifie une option d'un morceau précis.
    func setOption(for url: URL, _ keyPath: WritableKeyPath<TrackOptions, Bool>, to value: Bool) {
        guard let idx = items.firstIndex(where: { $0.url == url }) else { return }
        items[idx].options[keyPath: keyPath] = value
    }

    /// Applique une option à tous les morceaux et l'enregistre comme défaut.
    func setAll(_ keyPath: WritableKeyPath<TrackOptions, Bool>, to value: Bool) {
        defaultOptions[keyPath: keyPath] = value
        for idx in items.indices {
            items[idx].options[keyPath: keyPath] = value
        }
    }

    /// État agrégé d'une option sur l'ensemble des morceaux, pour une case à 3 états :
    /// `.on` si tous l'ont, `.off` si aucun, `.mixed` en cas de disparité.
    /// Liste vide → reflète `defaultOptions`.
    func aggregateState(_ keyPath: KeyPath<TrackOptions, Bool>) -> NSControl.StateValue {
        guard !items.isEmpty else {
            return defaultOptions[keyPath: keyPath] ? .on : .off
        }
        let allOn = items.allSatisfy { $0.options[keyPath: keyPath] }
        if allOn { return .on }
        let allOff = items.allSatisfy { !$0.options[keyPath: keyPath] }
        return allOff ? .off : .mixed
    }
}

/// Reçoit les fichiers ouverts via le Finder ou déposés sur l'icône du Dock.
final class AppDelegate: NSObject, NSApplicationDelegate {
    func application(_ application: NSApplication, open urls: [URL]) {
        Task { @MainActor in AppModel.shared.add(urls) }
    }
}
