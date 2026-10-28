import SwiftUI
import UniformTypeIdentifiers

struct ContentView: View {
    @EnvironmentObject private var model: AppModel
    @StateObject private var converter = Converter()

    @State private var customOutput = false
    @State private var outputRoot: URL? = nil
    @State private var dropTargeted = false
    /// Lignes sélectionnées dans la liste (sélection simple ou multiple).
    @State private var selection = Set<URL>()

    private var items: [InputItem] { model.items }
    private var fileCount: Int { Converter.expand(urls: items.map(\.url)).count }

    var body: some View {
        VStack(spacing: 14) {
            header

            filesZone

            optionsBox

            outputBox

            actionBar

            ConsoleView(text: converter.log)
        }
        .padding(18)
    }

    // MARK: - Sections

    private var header: some View {
        HStack {
            VStack(alignment: .leading, spacing: 2) {
                Text("XM2Live").font(.title2.bold())
                Text("Tracker (XM / MOD) → Ableton Live")
                    .font(.subheadline).foregroundStyle(.secondary)
            }
            Spacer()
        }
    }

    /// Zone unique : vide avec instructions au départ, se remplit avec la liste
    /// des morceaux ajoutés. Cible de drop, avec overlay pendant le glisser.
    private var filesZone: some View {
        VStack(alignment: .leading, spacing: 6) {
            HStack {
                Text(items.isEmpty
                     ? "Morceaux à convertir"
                     : "Morceaux à convertir — \(fileCount) fichier(s)")
                    .font(.subheadline.weight(.medium))
                Spacer()
                if !items.isEmpty {
                    Button("Tout effacer") { model.clear(); selection.removeAll() }
                        .buttonStyle(.borderless)
                        .font(.caption)
                }
            }

            ZStack {
                if items.isEmpty {
                    emptyState
                } else {
                    filledState
                }
            }
            .frame(maxWidth: .infinity, minHeight: 190, maxHeight: 260)
            .background(
                RoundedRectangle(cornerRadius: 12)
                    .fill(Color(nsColor: .controlBackgroundColor))
            )
            .overlay(
                RoundedRectangle(cornerRadius: 12)
                    .strokeBorder(style: StrokeStyle(lineWidth: 1.5, dash: [6]))
                    .foregroundStyle(dropTargeted ? Color.accentColor : Color.secondary.opacity(0.4))
            )
            .overlay {
                if dropTargeted { finderDropOverlay }
            }
            .clipShape(RoundedRectangle(cornerRadius: 12))
            .onDrop(of: [.fileURL], isTargeted: $dropTargeted) { providers in
                handleDrop(providers)
            }
            .animation(.easeInOut(duration: 0.15), value: dropTargeted)
        }
        // Garde la sélection cohérente si la liste change (suppression via X, effacement…).
        .onChange(of: items) { _, newItems in
            selection = selection.intersection(Set(newItems.map(\.url)))
        }
    }

    /// État vide : instructions centrées et bouton de sélection manuelle.
    private var emptyState: some View {
        VStack(spacing: 10) {
            Image(systemName: "tray.and.arrow.down")
                .font(.system(size: 34))
                .foregroundStyle(.secondary)
            Text("Glissez ici des fichiers .xm / .mod ou un dossier")
                .foregroundStyle(.secondary)
            Button("Choisir des fichiers…") { chooseFiles() }
                .buttonStyle(.bordered)
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
    }

    /// État rempli : liste sélectionnable + barre d'actions.
    private var filledState: some View {
        VStack(spacing: 0) {
            List(selection: $selection) {
                ForEach(items) { item in
                    fileRow(item).tag(item.url)
                }
            }
            .listStyle(.inset(alternatesRowBackgrounds: true))
            .scrollContentBackground(.hidden)
            .onDeleteCommand(perform: removeSelected)

            Divider()

            HStack(spacing: 8) {
                Text(selection.isEmpty
                     ? "Cmd/Maj-clic pour sélectionner plusieurs morceaux."
                     : "\(selection.count) morceau(x) sélectionné(s)")
                    .font(.caption).foregroundStyle(.secondary)
                Spacer()
                Button { chooseFiles() } label: {
                    Label("Ajouter…", systemImage: "plus")
                }
                .controlSize(.small)
                Button { removeSelected() } label: {
                    Label("Retirer la sélection", systemImage: "trash")
                }
                .controlSize(.small)
                .disabled(selection.isEmpty)
                .help("Retirer les morceaux sélectionnés (touche Suppr)")
            }
            .padding(.horizontal, 8)
            .padding(.vertical, 6)
        }
    }

    /// Overlay affiché pendant un glisser de fichiers (style SNFReels) :
    /// fond assombri, bord pointillé, gros « + » et libellé. Laisse passer
    /// le drop vers la zone sous-jacente (allowsHitTesting false).
    private var finderDropOverlay: some View {
        ZStack {
            Color.black.opacity(0.45)
            RoundedRectangle(cornerRadius: 12)
                .strokeBorder(
                    Color.white.opacity(0.6),
                    style: StrokeStyle(lineWidth: 2, dash: [8, 6])
                )
                .padding(8)
            VStack(spacing: 14) {
                Image(systemName: "plus")
                    .font(.system(size: 56, weight: .light))
                Text("Ajouter des morceaux")
                    .font(.system(size: 18, weight: .regular))
            }
            .foregroundStyle(Color.white.opacity(0.9))
        }
        .allowsHitTesting(false)
        .transition(.opacity)
    }

    private func fileRow(_ item: InputItem) -> some View {
        let url = item.url
        let isDir = Self.isDirectory(url)
        return HStack(spacing: 8) {
            Image(systemName: isDir ? "folder.fill" : "music.note")
                .foregroundStyle(isDir ? Color.accentColor : .secondary)
                .frame(width: 18)
            VStack(alignment: .leading, spacing: 1) {
                Text(url.lastPathComponent).lineLimit(1).truncationMode(.middle)
                Text(isDir
                     ? "Dossier — \(Converter.expand(urls: [url]).count) fichier(s)"
                     : url.deletingLastPathComponent().lastPathComponent)
                    .font(.caption2).foregroundStyle(.secondary)
                    .lineLimit(1).truncationMode(.middle)
            }
            Spacer()
            // Options de conversion propres à ce morceau (icônes activables).
            HStack(spacing: 1) {
                ForEach(trackOptionDescriptors) { desc in
                    optionIconButton(item: item, desc: desc)
                }
            }
            Button {
                remove(url)
            } label: {
                Image(systemName: "xmark.circle.fill")
                    .foregroundStyle(.secondary)
            }
            .buttonStyle(.borderless)
            .help("Retirer ce morceau")
        }
        .padding(.vertical, 2)
        .contentShape(Rectangle())
    }

    /// Bouton-icône d'une option pour un morceau : teinté si actif, atténué sinon.
    private func optionIconButton(item: InputItem, desc: OptionDescriptor) -> some View {
        let active = item.options[keyPath: desc.keyPath]
        return Button {
            model.setOption(for: item.url, desc.keyPath, to: !active)
        } label: {
            Image(systemName: desc.icon)
                .font(.system(size: 12))
                .foregroundStyle(active ? Color.optionIcon : Color.secondary.opacity(0.4))
                .frame(width: 22, height: 18)
                .contentShape(Rectangle())
        }
        .buttonStyle(.borderless)
        .help("\(desc.help) — \(active ? "activé" : "désactivé")")
    }

    private var optionsBox: some View {
        GroupBox("Options de conversion") {
            VStack(alignment: .leading, spacing: 6) {
                ForEach(trackOptionDescriptors) { desc in
                    let state = model.aggregateState(desc.keyPath)
                    HStack(spacing: 8) {
                        TriStateCheckbox(
                            title: "",
                            state: state,
                            onToggle: { newValue in model.setAll(desc.keyPath, to: newValue) }
                        )
                        .fixedSize()
                        // Icône (rappel de la légende des contrôles par ligne) + libellé.
                        HStack(spacing: 6) {
                            Image(systemName: desc.icon)
                                .font(.system(size: 12))
                                .foregroundStyle(Color.optionIcon)
                                .frame(width: 20)
                            Text(desc.label)
                        }
                        .contentShape(Rectangle())
                        .onTapGesture { model.setAll(desc.keyPath, to: state != .on) }
                        Spacer()
                    }
                }
                Text("S'applique à tous les morceaux — modifiable ligne par ligne.")
                    .font(.caption).foregroundStyle(.secondary)
                    .padding(.top, 2)
            }
            .frame(maxWidth: .infinity, alignment: .leading)
            .padding(4)
        }
    }

    private var outputBox: some View {
        GroupBox("Dossier de sortie") {
            VStack(alignment: .leading, spacing: 6) {
                Toggle("Dossier personnalisé", isOn: $customOutput)
                    .toggleStyle(.checkbox)
                    .onChange(of: customOutput) { _, on in
                        if on && outputRoot == nil {
                            // Différé : ouvrir le panneau pendant la mise à jour d'état
                            // SwiftUI gèle l'interaction. On le présente au cycle suivant.
                            DispatchQueue.main.async { chooseOutput() }
                        }
                        if !on { outputRoot = nil }
                    }
                if customOutput {
                    HStack {
                        Text(outputRoot?.path ?? "Aucun dossier choisi")
                            .font(.caption).foregroundStyle(.secondary)
                            .lineLimit(1).truncationMode(.middle)
                        Spacer()
                        Button("Parcourir…") { chooseOutput() }
                            .buttonStyle(.bordered).controlSize(.small)
                    }
                } else {
                    Text("À côté de chaque fichier source, dans « Conversions Ableton Live ».")
                        .font(.caption).foregroundStyle(.secondary)
                }
            }
            .frame(maxWidth: .infinity, alignment: .leading)
            .padding(4)
        }
    }

    private var actionBar: some View {
        HStack(spacing: 12) {
            if converter.isRunning {
                ProgressView().controlSize(.small)
                Text(converter.progressText).font(.caption).foregroundStyle(.secondary)
                    .lineLimit(1).truncationMode(.middle)
                Spacer()
                Button("Annuler") { converter.cancel() }
                    .buttonStyle(.bordered)
            } else {
                if !converter.outputDirs.isEmpty {
                    Button {
                        NSWorkspace.shared.activateFileViewerSelecting(converter.outputDirs)
                    } label: {
                        Label("Ouvrir le dossier de destination", systemImage: "folder")
                    }
                    .buttonStyle(.bordered)
                }
                Spacer()
                Button("Convertir") { startConversion() }
                    .buttonStyle(.borderedProminent)
                    .keyboardShortcut(.return, modifiers: [])
                    .disabled(items.isEmpty || (customOutput && outputRoot == nil))
            }
        }
    }

    // MARK: - Actions

    static func isDirectory(_ url: URL) -> Bool {
        var isDir: ObjCBool = false
        return FileManager.default.fileExists(atPath: url.path, isDirectory: &isDir) && isDir.boolValue
    }

    /// Retire un morceau (croix « X ») et nettoie la sélection.
    private func remove(_ url: URL) {
        model.remove(url)
        selection.remove(url)
    }

    /// Retire tous les morceaux actuellement sélectionnés.
    private func removeSelected() {
        guard !selection.isEmpty else { return }
        for url in selection { model.remove(url) }
        selection.removeAll()
    }

    private func startConversion() {
        converter.run(items: model.items, outputRoot: customOutput ? outputRoot : nil)
    }

    private func chooseFiles() {
        let panel = NSOpenPanel()
        panel.allowsMultipleSelection = true
        panel.canChooseDirectories = true
        panel.canChooseFiles = true
        if let xm = UTType(filenameExtension: "xm"), let mod = UTType(filenameExtension: "mod") {
            panel.allowedContentTypes = [xm, mod]
            panel.allowsOtherFileTypes = true
        }
        if panel.runModal() == .OK {
            model.set(panel.urls)
        }
    }

    private func chooseOutput() {
        let panel = NSOpenPanel()
        panel.canChooseDirectories = true
        panel.canChooseFiles = false
        panel.canCreateDirectories = true
        panel.prompt = "Choisir"
        if panel.runModal() == .OK, let url = panel.url {
            outputRoot = url
        } else if outputRoot == nil {
            customOutput = false
        }
    }

    private func handleDrop(_ providers: [NSItemProvider]) -> Bool {
        let group = DispatchGroup()
        var collected: [URL] = []
        for provider in providers {
            group.enter()
            _ = provider.loadObject(ofClass: URL.self) { url, _ in
                if let url { collected.append(url) }
                group.leave()
            }
        }
        group.notify(queue: .main) {
            if !collected.isEmpty { model.add(collected) }
        }
        return true
    }
}

/// Console à défilement automatique vers le bas.
struct ConsoleView: View {
    let text: String

    var body: some View {
        ScrollViewReader { proxy in
            ScrollView {
                Text(text.isEmpty ? "La sortie de conversion apparaîtra ici." : text)
                    .font(.system(.caption, design: .monospaced))
                    .foregroundStyle(text.isEmpty ? .secondary : .primary)
                    .textSelection(.enabled)
                    .frame(maxWidth: .infinity, alignment: .leading)
                    .padding(8)
                Color.clear.frame(height: 1).id("bottom")
            }
            .background(RoundedRectangle(cornerRadius: 8).fill(Color(nsColor: .textBackgroundColor)))
            .frame(maxWidth: .infinity, maxHeight: .infinity)
            .onChange(of: text) { _, _ in
                withAnimation(.linear(duration: 0.1)) { proxy.scrollTo("bottom", anchor: .bottom) }
            }
        }
    }
}
