import SwiftUI
import AppKit

extension Color {
    /// Teinte des icônes d'options (#E5AC8D).
    static let optionIcon = Color(red: 229.0 / 255.0, green: 172.0 / 255.0, blue: 141.0 / 255.0)
}

/// Décrit une option de conversion : son champ dans `TrackOptions`, son icône
/// (boutons par ligne), son libellé (case globale) et son infobulle.
struct OptionDescriptor: Identifiable {
    let id: String
    let keyPath: WritableKeyPath<TrackOptions, Bool>
    let icon: String
    let label: String
    let help: String
}

/// Les 4 options de conversion, dans l'ordre d'affichage.
let trackOptionDescriptors: [OptionDescriptor] = [
    OptionDescriptor(id: "pan", keyPath: \.panAutomation,
                     icon: "arrow.left.and.right",
                     label: "Pan automation (effet 8xx)",
                     help: "Pan automation (effet 8xx)"),
    OptionDescriptor(id: "offset", keyPath: \.sampleOffset,
                     icon: "waveform.path",
                     label: "Sample offset (effet 9xx, via Simpler)",
                     help: "Sample offset (effet 9xx, via Simpler)"),
    OptionDescriptor(id: "env", keyPath: \.envelope,
                     icon: "alternatingcurrent",
                     label: "Enveloppes FT2 → ADSR (expérimental)",
                     help: "Enveloppes FT2 → ADSR (expérimental)"),
    OptionDescriptor(id: "merge", keyPath: \.mergeTracks,
                     icon: "arrow.triangle.merge",
                     label: "Merge tracks (piste « All notes » par instrument)",
                     help: "Merge tracks (piste « All notes » par instrument)"),
]

/// Case à cocher à 3 états (vide / cochée / « tiret » bleu) basée sur un
/// `NSButton` natif. L'état affiché est piloté par les données ; le clic ne
/// suit PAS le cyclage natif : il applique « tout activé » sauf si déjà tout
/// activé, auquel cas « tout désactivé ». L'état mixte n'apparaît donc qu'en
/// conséquence d'une disparité, jamais comme cible de clic.
struct TriStateCheckbox: NSViewRepresentable {
    let title: String
    let state: NSControl.StateValue
    /// Appelé au clic avec la valeur voulue pour toutes les lignes.
    let onToggle: (Bool) -> Void

    func makeNSView(context: Context) -> NSButton {
        let button = NSButton(checkboxWithTitle: title,
                              target: context.coordinator,
                              action: #selector(Coordinator.clicked(_:)))
        button.allowsMixedState = true
        button.state = state
        return button
    }

    func updateNSView(_ button: NSButton, context: Context) {
        context.coordinator.parent = self
        button.title = title
        button.state = state
    }

    func makeCoordinator() -> Coordinator { Coordinator(self) }

    final class Coordinator: NSObject {
        var parent: TriStateCheckbox
        init(_ parent: TriStateCheckbox) { self.parent = parent }

        @objc func clicked(_ sender: NSButton) {
            // Ignore le nouvel état natif : on décide d'après l'état courant.
            let newValue = (parent.state != .on)
            // Remet l'apparence en phase ; SwiftUI la recalcule ensuite via les données.
            sender.state = newValue ? .on : .off
            parent.onToggle(newValue)
        }
    }
}
