'use strict';

/**
 * PyTango Linter — VS Code extension.
 *
 * Runs pytangolint.py as a subprocess whenever a Python file is opened or
 * saved, then surfaces the results as VS Code diagnostics (squiggles +
 * Problems panel).
 *
 * No compilation step required; this file is loaded directly by VS Code.
 */

const vscode = require('vscode');
const cp     = require('child_process');
const path   = require('path');
const fs     = require('fs');

// ── Module-level state ────────────────────────────────────────────────────────

/** @type {vscode.DiagnosticCollection} */
let diagnosticCollection;

/** @type {vscode.StatusBarItem} */
let statusBarItem;

/** Debounce timers keyed by document URI string. */
const debounceTimers = new Map();

// ── Parsing ───────────────────────────────────────────────────────────────────

/**
 * Matches one pytangolint output line, e.g.:
 *   path/to/file.py:10:4: warning: T023 Attribute 'foo' needs 'description'
 *
 * Groups: (path)(line)(col)(severity)(code)(message)
 * The code group uses [A-Z]\d+ to anchor the match from the right, preventing
 * ambiguous splits on paths that contain colons (e.g. Windows drive letters).
 */
const ISSUE_RE = /^(.*):(\d+):(\d+): (error|warning|info): ([A-Z]\d+) (.+)$/;

/** @param {string} severity */
function toVSCodeSeverity(severity) {
    switch (severity) {
        case 'error':   return vscode.DiagnosticSeverity.Error;
        case 'warning': return vscode.DiagnosticSeverity.Warning;
        default:        return vscode.DiagnosticSeverity.Information;
    }
}

/**
 * Parse pytangolint --no-color stdout into an array of VS Code Diagnostics.
 * Lines that do not match the issue format are silently ignored (separator
 * lines, summary lines, "✓ No issues found", etc.).
 *
 * @param {string} stdout
 * @returns {vscode.Diagnostic[]}
 */
function parseOutput(stdout) {
    const diagnostics = [];
    for (const line of stdout.split('\n')) {
        const m = line.match(ISSUE_RE);
        if (!m) continue;

        const [, , lineStr, colStr, severity, code, message] = m;
        const lineNum = Math.max(0, parseInt(lineStr, 10) - 1); // 0-based
        const colNum  = Math.max(0, parseInt(colStr,  10));

        const range = new vscode.Range(lineNum, colNum, lineNum, 9999);
        const diag  = new vscode.Diagnostic(
            range,
            `${code}: ${message}`,
            toVSCodeSeverity(severity)
        );
        diag.source = 'pytangolint';
        diag.code   = code;
        diagnostics.push(diag);
    }
    return diagnostics;
}

// ── Path resolution ───────────────────────────────────────────────────────────

/**
 * Locate pytangolint.py for the given document.
 * Search order:
 *   1. pytangolint.linterPath setting (if set)
 *   2. pytangolint.py bundled inside this extension (always available)
 *   3. pytangolint.py in the workspace root of the document (legacy fallback)
 *
 * @param {vscode.TextDocument} document
 * @returns {string|null}
 */
function findLinterPath(document) {
    const cfg = vscode.workspace.getConfiguration('pytangolint');
    const configured = cfg.get('linterPath', '').trim();
    if (configured && fs.existsSync(configured)) return configured;

    // Bundled copy inside the extension directory (always present).
    const bundled = path.join(__dirname, 'pytangolint.py');
    if (fs.existsSync(bundled)) return bundled;

    // Legacy: pytangolint.py in the workspace root.
    const wsFolder = vscode.workspace.getWorkspaceFolder(document.uri);
    if (wsFolder) {
        const candidate = path.join(wsFolder.uri.fsPath, 'pytangolint.py');
        if (fs.existsSync(candidate)) return candidate;
    }

    return null;
}

/**
 * Resolve the Python interpreter to use.
 * Preference order:
 *   1. pytangolint.pythonPath setting (if set)
 *   2. Active interpreter from the Microsoft Python extension
 *   3. 'python3'
 *
 * @returns {string}
 */
function getPythonPath() {
    const cfg = vscode.workspace.getConfiguration('pytangolint');
    const configured = cfg.get('pythonPath', '').trim();
    if (configured) return configured;

    try {
        const pythonExt = vscode.extensions.getExtension('ms-python.python');
        if (pythonExt?.isActive) {
            const exec = pythonExt.exports?.settings
                ?.getExecutionDetails?.()?.execCommand;
            if (Array.isArray(exec) && exec.length > 0) return exec[0];
        }
    } catch (_) { /* Python extension not available or its API changed */ }

    return 'python3';
}

// ── Status bar helpers ────────────────────────────────────────────────────────

function statusRunning() {
    statusBarItem.text    = '$(sync~spin) PyTango';
    statusBarItem.tooltip = 'PyTango Linter: running…';
    statusBarItem.show();
}

/** @param {vscode.Diagnostic[]} diagnostics */
function statusDone(diagnostics) {
    const errors   = diagnostics.filter(d => d.severity === vscode.DiagnosticSeverity.Error).length;
    const warnings = diagnostics.filter(d => d.severity === vscode.DiagnosticSeverity.Warning).length;

    if (errors > 0) {
        statusBarItem.text    = `$(error) PyTango: ${errors}E ${warnings}W`;
        statusBarItem.tooltip = `PyTango Linter: ${errors} error(s), ${warnings} warning(s)`;
    } else if (warnings > 0) {
        statusBarItem.text    = `$(warning) PyTango: ${warnings}W`;
        statusBarItem.tooltip = `PyTango Linter: ${warnings} warning(s)`;
    } else {
        statusBarItem.text    = '$(check) PyTango';
        statusBarItem.tooltip = 'PyTango Linter: no issues';
    }
}

function statusError(message) {
    statusBarItem.text    = '$(alert) PyTango';
    statusBarItem.tooltip = `PyTango Linter: ${message}`;
    statusBarItem.show();
}

// ── Disabled-rules helpers ────────────────────────────────────────────────────

/** All rule codes defined in the extension. */
const ALL_RULE_CODES = [
    'T001','T010','T011','T020','T021','T022','T023','T024','T025',
    'T030','T031','T032',
    'G001','G002','G003','G004','G005','G006','G007','G008',
];

/**
 * Read the per-rule boolean settings and return an array of codes to disable.
 * @returns {string[]}
 */
function getDisabledRules() {
    const cfg = vscode.workspace.getConfiguration('pytangolint');
    return ALL_RULE_CODES.filter(code => cfg.get(`rules.${code}`, true) === false);
}

// ── Core lint runner ──────────────────────────────────────────────────────────

/**
 * Run pytangolint on a single document and update the diagnostic collection.
 *
 * @param {vscode.TextDocument} document
 */
function lintDocument(document) {
    // Only lint saved Python files (not untitled buffers, output panes, etc.)
    if (document.uri.scheme !== 'file' || document.languageId !== 'python') {
        return;
    }

    const linterPath = findLinterPath(document);
    if (!linterPath) {
        // pytangolint.py not found — clear stale diagnostics and stay silent
        diagnosticCollection.delete(document.uri);
        return;
    }

    const pythonPath = getPythonPath();
    const filePath   = document.uri.fsPath;

    // Build --disable args for any rules the user has turned off.
    const disabledArgs = getDisabledRules().flatMap(code => ['--disable', code]);

    statusRunning();

    cp.execFile(
        pythonPath,
        [linterPath, '--no-color', ...disabledArgs, filePath],
        {
            cwd:       path.dirname(linterPath),
            maxBuffer: 1024 * 1024, // 1 MB — more than enough for lint output
        },
        (err, stdout, stderr) => {
            // Non-zero exit codes (1 = issues found) are expected; only log
            // unexpected stderr (e.g. Python import errors, missing modules).
            if (stderr && stderr.trim()) {
                console.error('[pytangolint]', stderr.trim());
                statusError(stderr.trim().split('\n')[0]);
                return;
            }

            const diagnostics = parseOutput(stdout);
            diagnosticCollection.set(document.uri, diagnostics);
            statusDone(diagnostics);
        }
    );
}

// ── Activation / deactivation ─────────────────────────────────────────────────

/**
 * Called by VS Code when the extension is first activated
 * (i.e. when a Python file is opened).
 *
 * @param {vscode.ExtensionContext} context
 */
function activate(context) {
    diagnosticCollection = vscode.languages.createDiagnosticCollection('pytangolint');

    statusBarItem = vscode.window.createStatusBarItem(
        vscode.StatusBarAlignment.Left, 100
    );
    statusBarItem.command = 'workbench.action.problems.focus';

    context.subscriptions.push(diagnosticCollection, statusBarItem);

    // ── Event subscriptions ────────────────────────────────────────────────

    const cfg = () => vscode.workspace.getConfiguration('pytangolint');

    context.subscriptions.push(
        vscode.workspace.onDidOpenTextDocument(doc => {
            if (cfg().get('lintOnOpen', true)) lintDocument(doc);
        }),

        vscode.workspace.onDidSaveTextDocument(doc => {
            if (cfg().get('lintOnSave', true)) lintDocument(doc);
        }),

        vscode.workspace.onDidChangeTextDocument(event => {
            if (!cfg().get('lintOnChange', false)) return;
            const doc = event.document;
            if (doc.languageId !== 'python') return;

            // Debounce: don't re-lint on every keystroke
            const key = doc.uri.toString();
            if (debounceTimers.has(key)) clearTimeout(debounceTimers.get(key));
            debounceTimers.set(key, setTimeout(() => {
                debounceTimers.delete(key);
                lintDocument(doc);
            }, 600));
        }),

        vscode.workspace.onDidCloseTextDocument(doc => {
            // Remove diagnostics when a file is closed
            diagnosticCollection.delete(doc.uri);
            const key = doc.uri.toString();
            if (debounceTimers.has(key)) clearTimeout(debounceTimers.get(key));
            debounceTimers.delete(key);
        }),

        // Show/hide status bar based on active editor language
        vscode.window.onDidChangeActiveTextEditor(editor => {
            if (editor?.document.languageId === 'python') {
                statusBarItem.show();
            } else {
                statusBarItem.hide();
            }
        }),

        // Register a manual "lint this file" command
        vscode.commands.registerCommand('pytangolint.lintFile', () => {
            const editor = vscode.window.activeTextEditor;
            if (editor) lintDocument(editor.document);
        })
    );

    // ── Lint already-open documents at startup ─────────────────────────────
    if (cfg().get('lintOnOpen', true)) {
        vscode.workspace.textDocuments.forEach(doc => lintDocument(doc));
    }

    // Show status bar if a Python file is already active
    if (vscode.window.activeTextEditor?.document.languageId === 'python') {
        statusBarItem.show();
    }
}

function deactivate() {
    for (const timer of debounceTimers.values()) clearTimeout(timer);
    debounceTimers.clear();
    diagnosticCollection?.clear();
    diagnosticCollection?.dispose();
    statusBarItem?.dispose();
}

module.exports = { activate, deactivate };
