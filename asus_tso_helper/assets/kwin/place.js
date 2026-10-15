// asus-tso-helper: the main window opens next to where it was opened from (the tray icon), as
// G-Helper's does above the taskbar. Wayland apps cannot place their own windows, KWin can.
function place(window) {
    if (window.resourceClass !== "asus-tso-helper" || window.caption.indexOf("asus-tso-helper") !== 0)
        return;
    var cursor = workspace.cursorPos;
    var screen = workspace.screenAt ? workspace.screenAt(cursor) : workspace.activeScreen;
    var area = workspace.clientArea(KWin.MaximizeArea, screen, workspace.currentDesktop);
    var g = window.frameGeometry;
    var margin = 8;
    // centred on the cursor, kept inside the work area: next to the panel when opened from it
    var x = Math.min(Math.max(cursor.x - g.width / 2, area.x + margin), area.x + area.width - g.width - margin);
    var y = Math.min(Math.max(cursor.y - g.height / 2, area.y + margin), area.y + area.height - g.height - margin);
    window.frameGeometry = {x: Math.round(x), y: Math.round(y), width: g.width, height: g.height};
}
workspace.windowAdded.connect(place);
