import AppKit
import WebKit

final class CloseHandler: NSObject, WKScriptMessageHandler {
    weak var app: NSApplication?
    func userContentController(_ userContentController: WKUserContentController, didReceive message: WKScriptMessage) {
        app?.terminate(nil)
    }
}

// Snapshots the receipt and lets the user save it as a PNG anywhere they like.
final class SaveImageHandler: NSObject, WKScriptMessageHandler {
    weak var webView: WKWebView?
    weak var window: NSWindow?
    func userContentController(_ userContentController: WKUserContentController, didReceive message: WKScriptMessage) {
        guard let webView = webView else { return }
        // A long receipt drapes off-screen (clipped by the paper window), so a
        // plain snapshot of the visible view would omit the lower sections.
        // Ask the page to flatten to its full height, grow the web view to that
        // height so WebKit lays out and renders the whole receipt, snapshot it,
        // then restore the view and the page's interactive layout.
        let originalFrame = webView.frame
        webView.evaluateJavaScript("window.__arBeginExport && window.__arBeginExport()") { result, _ in
            var fullWidth = originalFrame.width
            var fullHeight = originalFrame.height
            if let dims = result as? [String: Any] {
                if let w = dims["width"] as? Double, w > 0 { fullWidth = CGFloat(w) }
                if let h = dims["height"] as? Double, h > 0 { fullHeight = CGFloat(h) }
            }
            webView.frame = NSRect(x: 0, y: 0, width: fullWidth, height: fullHeight)
            // Give layout a beat to settle at the new height before snapshotting.
            DispatchQueue.main.asyncAfter(deadline: .now() + 0.25) {
                let config = WKSnapshotConfiguration()
                config.rect = NSRect(x: 0, y: 0, width: fullWidth, height: fullHeight)
                webView.takeSnapshot(with: config) { image, _ in
                    DispatchQueue.main.async {
                        webView.frame = originalFrame
                        webView.evaluateJavaScript("window.__arEndExport && window.__arEndExport()", completionHandler: nil)
                        self.presentSavePanel(for: image)
                    }
                }
            }
        }
    }

    private func presentSavePanel(for image: NSImage?) {
        guard let image = image,
              let tiff = image.tiffRepresentation,
              let rep = NSBitmapImageRep(data: tiff),
              let png = rep.representation(using: .png, properties: [:]) else { return }
        let panel = NSSavePanel()
        panel.allowedFileTypes = ["png"]
        panel.nameFieldStringValue = "agent-receipt.png"
        panel.canCreateDirectories = true
        NSApp.activate(ignoringOtherApps: true)
        let write: (NSApplication.ModalResponse) -> Void = { response in
            if response == .OK, let url = panel.url {
                try? png.write(to: url)
            }
        }
        // The receipt window floats above normal windows, so a free-standing
        // panel would open behind it. Attaching it as a sheet keeps it in
        // front of the receipt; fall back to a raised-level panel.
        if let window = self.window {
            panel.beginSheetModal(for: window, completionHandler: write)
        } else {
            panel.level = .modalPanel
            panel.begin(completionHandler: write)
        }
    }
}

final class AppDelegate: NSObject, NSApplicationDelegate {
    var window: NSWindow!
    var webView: WKWebView!
    let closeHandler = CloseHandler()
    let saveHandler = SaveImageHandler()

    func applicationDidFinishLaunching(_ notification: Notification) {
        guard CommandLine.arguments.count > 1 else {
            NSApp.terminate(nil)
            return
        }

        let path = CommandLine.arguments[1]
        let fileURL = URL(fileURLWithPath: path)
        let accessURL = fileURL.deletingLastPathComponent()
        let screen = activeScreen()

        let config = WKWebViewConfiguration()
        let controller = WKUserContentController()
        controller.add(closeHandler, name: "close")
        controller.add(saveHandler, name: "saveImage")
        // All close/drag interaction is owned by receipt.js (which posts to the
        // `close` message handler below). The bridge only tags the document as
        // native and keeps Escape as a guaranteed fallback — it must NOT add a
        // click-to-close listener: pointer capture during a drag retargets the
        // synthetic click to the stage, which such a listener would misread as a
        // click outside the receipt and close it on every drag or paper click.
        let bridge = """
        (function () {
          document.documentElement.classList.add('native-viewer');
          document.addEventListener('keydown', function(e) {
            if (e.key === 'Escape') {
              e.preventDefault();
              try { window.webkit.messageHandlers.close.postMessage('close'); } catch (err) {}
            }
          });
        })();
        """
        controller.addUserScript(WKUserScript(source: bridge, injectionTime: .atDocumentEnd, forMainFrameOnly: true))
        config.userContentController = controller

        webView = WKWebView(frame: screen.visibleFrame, configuration: config)
        webView.setValue(false, forKey: "drawsBackground")
        webView.allowsMagnification = false

        window = NSWindow(
            contentRect: screen.frame,
            styleMask: [.borderless],
            backing: .buffered,
            defer: false,
            screen: screen
        )
        window.isOpaque = false
        window.backgroundColor = .clear
        window.hasShadow = false
        window.level = .floating
        window.collectionBehavior = [.canJoinAllSpaces, .fullScreenAuxiliary]
        window.contentView = webView
        window.ignoresMouseEvents = false

        closeHandler.app = NSApp
        saveHandler.webView = webView
        saveHandler.window = window
        NSApp.setActivationPolicy(.accessory)
        NSApp.activate(ignoringOtherApps: true)
        window.makeKeyAndOrderFront(nil)
        webView.loadFileURL(fileURL, allowingReadAccessTo: accessURL)
    }

    private func activeScreen() -> NSScreen {
        if let main = NSScreen.main {
            return main
        }
        let mouse = NSEvent.mouseLocation
        if let screen = NSScreen.screens.first(where: { $0.frame.contains(mouse) }) {
            return screen
        }
        return NSScreen.screens[0]
    }

    func applicationShouldTerminateAfterLastWindowClosed(_ sender: NSApplication) -> Bool { true }
}

let app = NSApplication.shared
let delegate = AppDelegate()
app.delegate = delegate
app.run()
