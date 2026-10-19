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

function nearBottom(g, area) {
    // the window sits nearer the work area's bottom (a panel at the bottom) than its top
    return area.y + area.height - (g.y + g.height) < g.y - area.y;
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
    // edges level on the panel's side (bottoms above a bottom panel, tops under a top one); kept
    // inside the work area
    var y = nearBottom(m, area) ? m.y + m.height - g.height : m.y;
    y = clamp(y, area.y + MARGIN, area.y + area.height - g.height - MARGIN);
    window.frameGeometry = {x: Math.round(x), y: Math.round(y), width: g.width, height: g.height};
}

function keepPanelEdge(window) {
    // the app changed the window's height (a section folded, the GPU note): Wayland keeps the top
    // edge, which is right under a top panel; above a bottom panel the bottom edge goes back where
    // it was instead. Not while the user drags an edge.
    window.frameGeometryChanged.connect(function (a, b) {
        var old = b || a;                           // KWin 6 passes the old geometry, KWin 5 the window first
        var g = window.frameGeometry;
        if (!old || window.move || window.resize || g.height === old.height || g.width !== old.width)
            return;
        var area = workArea(window.output || workspace.activeScreen);
        // the panel's side is where the main window opened (from the tray); a tall window beside it
        // can reach nearer the other edge
        var main = isMain(window) ? null : mainWindow();
        if (!nearBottom(main ? main.frameGeometry : old, area))
            return;
        var y = clamp(old.y + old.height - g.height, area.y + MARGIN, area.y + area.height - g.height - MARGIN);
        if (Math.round(y) !== Math.round(g.y))
            window.frameGeometry = {x: g.x, y: Math.round(y), width: g.width, height: g.height};
    });
}

function place(window) {
    if (!ours(window) || window.dialog || window.specialWindow)
        return;                                     // message boxes stay centred on their window
    window.keepAbove = KEEP_ABOVE;
    if (isMain(window))
        placeMain(window);
    else if (mainWindow())
        placeBeside(window, mainWindow());
    keepPanelEdge(window);
}
workspace.windowAdded.connect(place);

// "Keep app window always on top" toggled: the script is reloaded, already open windows follow
(function () {
    var list = workspace.windowList ? workspace.windowList() : workspace.clientList();
    for (var i = 0; i < list.length; i++)
        if (ours(list[i]) && !list[i].dialog && !list[i].specialWindow) {
            list[i].keepAbove = KEEP_ABOVE;
            keepPanelEdge(list[i]);
        }
})();
