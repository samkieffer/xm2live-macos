import SwiftUI
import UniformTypeIdentifiers

struct ContentView: View {
    @EnvironmentObject private var model: AppModel
    @StateObject private var converter = Converter()

    @State private var options = ConversionOptions()
    @State private var customOutput = false
    @State private var outputRoot: URL? = nil
    @State private var dropTargeted = false

    private var inputs: [URL] { model.inputs }
    private var fileCount: Int { Converter.expand(urls: inputs).count }

    var body: some View {
        VStack(spacing: 14) {
            header

            dropZone

            if !inputs.isEmpty {
                fileListView
            }

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

    private var dropZone: some View {
        VStack(spacing: 8) {
            Image(systemName: "tray.and.arrow.down")
                .font(.system(size: 30))
                .foregroundStyle(dropTargeted ? Color.accentColor : .secondary)
            if inputs.isEmpty {
                Text("Glissez ici des fichiers .xm / .mod ou un dossier")
                    .foregroundStyle(.secondary)
            } else {
                Text("\(inputs.count) élément(s) sélectionné(s) — \(fileCount) fichier(s) à convertir")
                    .foregroundStyle(.primary)
            }
            Button("Choisir des fichiers…") { chooseFiles() }
                .buttonStyle(.bordered)
            if !inputs.isEmpty {
                Button("Effacer la sélection") { model.clear() }
                    .buttonStyle(.borderless)
                    .font(.caption)
            }
        }
        .frame(maxWidth: .infinity)
        .padding(.vertical, 22)
        .background(
            RoundedRectangle(cornerRadius: 12)
                .fill(Color(nsColor: .controlBackgroundColor))
        )
        .overlay(
            RoundedRectangle(cornerRadius: 12)
                .strokeBorder(style: StrokeStyle(lineWidth: 1.5, dash: [6]))
                .foregroundStyle(dropTargeted ? Color.accentColor : Color.secondary.opacity(0.4))
        )
        .onDrop(of: [.fileURL], isTargeted: $dropTargeted) { providers in
            handleDrop(providers)
        }
    }

    private var fileListView: some View {
        GroupBox {
            ScrollView {
                VStack(spacing: 2) {
                    ForEach(inputs, id: \.self) { url in
                        fileRow(url)
                        if url != inputs.last { Divider() }
                    }
                }
                .padding(4)
            }
            .frame(maxHeight: 150)
        } label: {
            Text("Morceaux à convertir — \(fileCount) fichier(s)")
        }
    }

    private func fileRow(_ url: URL) -> some View {
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
            Button {
                model.remove(url)
            } label: {
                Image(systemName: "xmark.circle.fill")
                    .foregroundStyle(.secondary)
            }
            .buttonStyle(.borderless)
            .help("Retirer de la sélection")
        }
        .padding(.vertical, 2)
        .contentShape(Rectangle())
    }

    private var optionsBox: some View {
        GroupBox("Options de conversion") {
            VStack(alignment: .leading, spacing: 6) {
                Toggle("Pan automation (effet 8xx)", isOn: $options.panAutomation)
                Toggle("Sample offset (effet 9xx, via Simpler)", isOn: $options.sampleOffset)
                Toggle("Enveloppes FT2 → ADSR (expérimental)", isOn: $options.envelope)
                Toggle("Merge tracks (piste « All notes » par instrument)", isOn: $options.mergeTracks)
            }
            .toggleStyle(.checkbox)
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
                    .disabled(inputs.isEmpty || (customOutput && outputRoot == nil))
            }
        }
    }

    // MARK: - Actions

    static func isDirectory(_ url: URL) -> Bool {
        var isDir: ObjCBool = false
        return FileManager.default.fileExists(atPath: url.path, isDirectory: &isDir) && isDir.boolValue
    }

    private func startConversion() {
        options.outputRoot = customOutput ? outputRoot : nil
        converter.run(inputs: inputs, options: options)
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
