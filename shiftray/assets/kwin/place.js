// shiftray: the main window opens next to where it was opened from (the tray icon), as
// G-Helper's does above the taskbar; its other windows (Fans, Extra, Updates, Setup) open beside
// it, left or right where there is room, as G-Helper's do. Wayland apps cannot place their own
// windows, KWin can.
// KEEP_ABOVE is prepended by the app when it loads the script (Extra -> always on top)
var MARGIN = 8;

function ours(window) {
    return window.resourceClass === "shiftray";
}

function isMain(window) {
    return ours(window) && window.caption.indexOf("Shiftray") === 0;
}

function clamp(value, low, high) {
    return Math.min(Math.max(value, low), high);
}

function workArea(screen) {
    return workspace.clientArea(KWin.MaximizeArea, screen, workspace.currentDesktop);
}

function mainWindow() {
    var list = workspace.windowList ? workspace.windowList() : workspace.clientList();
    for (var i = 0; i < list.length; i++)
        if (isMain(list[i]) && !list[i].minimized)
            return list[i];
    return null;
}

function placeMain(window) {
    // centred on the cursor, kept inside the work area: next to the panel when opened from it
    var cursor = workspace.cursorPos;
    var area = workArea(workspace.screenAt ? workspace.screenAt(cursor) : workspace.activeScreen);
    var g = window.frameGeometry;
    var x = clamp(cursor.x - g.width / 2, area.x + MARGIN, area.x + area.width - g.width - MARGIN);
    var y = clamp(cursor.y - g.height / 2, area.y + MARGIN, area.y + area.height - g.height - MARGIN);
    window.frameGeometry = {x: Math.round(x), y: Math.round(y), width: g.width, height: g.height};
}

function placeBeside(window, main) {
    var m = main.frameGeometry;
    var area = workArea(main.output || workspace.activeScreen);
    var g = window.frameGeometry;
    var left = m.x - MARGIN - g.width;
    var right = m.x + m.width + MARGIN;
    var x;
    if (left >= area.x)
        x = left;                                   // G-Helper's side: the main window sits at the tray
    else if (right + g.width <= area.x + area.width)
        x = right;
    else                                            // no room either side: the wider side, overlapping
        x = m.x - area.x > area.x + area.width - m.x - m.width ? area.x + MARGIN
                                                                : area.x + area.width - g.width - MARGIN;
    // bottom edges level, as both sit above the panel; kept inside the work area
    var y = clamp(m.y + m.height - g.height, area.y + MARGIN, area.y + area.height - g.height - MARGIN);
    window.frameGeometry = {x: Math.round(x), y: Math.round(y), width: g.width, height: g.height};
}

function place(window) {
    if (!ours(window) || window.dialog || window.specialWindow)
        return;                                     // message boxes stay centred on their window
    window.keepAbove = KEEP_ABOVE;
    if (isMain(window)) {
        placeMain(window);
        return;
    }
    var main = mainWindow();
    if (main)
        placeBeside(window, main);
}
workspace.windowAdded.connect(place);

// "Keep app window always on top" toggled: the script is reloaded, already open windows follow
(function () {
    var list = workspace.windowList ? workspace.windowList() : workspace.clientList();
    for (var i = 0; i < list.length; i++)
        if (ours(list[i]) && !list[i].dialog && !list[i].specialWindow)
            list[i].keepAbove = KEEP_ABOVE;
})();
