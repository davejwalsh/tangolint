'use strict';

/**
 * TangoLint — VS Code extension.
 *
 * Runs tangolint.py as a subprocess whenever a Python file is opened or
 * saved, then surfaces the results as VS Code diagnostics (squiggles +
 * Problems panel).
 *
 * No compilation step required; this file is loaded directly by VS Code.
 */

const vscode = require('vscode');
const cp     = require('child_process');
const path   = require('path');
const fs     = require('fs');

// Resolved during activate() — points to the deployed copy of tangolint.py.
let deployedLinterPath = null;

// ── Module-level state ────────────────────────────────────────────────────────

/** @type {vscode.DiagnosticCollection} */
let diagnosticCollection;

/** @type {vscode.StatusBarItem} */
let statusBarItem;

/** Debounce timers keyed by document URI string. */
const debounceTimers = new Map();

// ── Parsing ───────────────────────────────────────────────────────────────────

/**
 * Matches one TangoLint output line, e.g.:
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
 * Parse TangoLint --no-color stdout into an array of VS Code Diagnostics.
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
        diag.source = 'tangolint';
        diag.code   = code;
        diagnostics.push(diag);
    }
    return diagnostics;
}

// ── Path resolution ───────────────────────────────────────────────────────────

/**
 * Locate tangolint.py for the given document.
 * Search order:
 *   1. tangolint.linterPath setting (if set and exists)
 *   2. Scripts deployed to globalStorage during activate()
 *   3. Workspace root (legacy fallback)
 *
 * @param {vscode.TextDocument} document
 * @returns {string|null}
 */
function findLinterPath(document) {
    const cfg = vscode.workspace.getConfiguration('tangolint');
    const configured = cfg.get('linterPath', '').trim();
    if (configured && fs.existsSync(configured)) return configured;

    if (deployedLinterPath && fs.existsSync(deployedLinterPath)) return deployedLinterPath;

    // Legacy: tangolint.py in the workspace root.
    const wsFolder = vscode.workspace.getWorkspaceFolder(document.uri);
    if (wsFolder) {
        const candidate = path.join(wsFolder.uri.fsPath, 'tangolint.py');
        if (fs.existsSync(candidate)) return candidate;
    }

    return null;
}

/**
 * Resolve the Python interpreter to use.
 * Preference order:
 *   1. tangolint.pythonPath setting (if set)
 *   2. Active interpreter from the Microsoft Python extension
 *   3. 'python3'
 *
 * @returns {string}
 */
function getPythonPath() {
    const cfg = vscode.workspace.getConfiguration('tangolint');
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
    statusBarItem.text    = '$(sync~spin) TangoLint';
    statusBarItem.tooltip = 'TangoLint: running…';
    statusBarItem.show();
}

/** @param {vscode.Diagnostic[]} diagnostics */
function statusDone(diagnostics) {
    const errors   = diagnostics.filter(d => d.severity === vscode.DiagnosticSeverity.Error).length;
    const warnings = diagnostics.filter(d => d.severity === vscode.DiagnosticSeverity.Warning).length;

    if (errors > 0) {
        statusBarItem.text    = `$(error) TangoLint: ${errors}E ${warnings}W`;
        statusBarItem.tooltip = `TangoLint: ${errors} error(s), ${warnings} warning(s)`;
    } else if (warnings > 0) {
        statusBarItem.text    = `$(warning) TangoLint: ${warnings}W`;
        statusBarItem.tooltip = `TangoLint: ${warnings} warning(s)`;
    } else {
        statusBarItem.text    = '$(check) TangoLint';
        statusBarItem.tooltip = 'TangoLint: no issues';
    }
}

function statusError(message) {
    statusBarItem.text    = '$(alert) TangoLint';
    statusBarItem.tooltip = `TangoLint: ${message}`;
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
    const cfg = vscode.workspace.getConfiguration('tangolint');
    return ALL_RULE_CODES.filter(code => cfg.get(`rules.${code}`, true) === false);
}

// ── Core lint runner ──────────────────────────────────────────────────────────

/**
 * Run TangoLint on a single document and update the diagnostic collection.
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
        // tangolint.py not found — clear stale diagnostics and stay silent
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
                console.error('[tangolint]', stderr.trim());
                statusError(stderr.trim().split('\n')[0]);
                return;
            }

            const diagnostics = parseOutput(stdout);
            diagnosticCollection.set(document.uri, diagnostics);
            statusDone(diagnostics);
        }
    );
}

// ── Script deployment ─────────────────────────────────────────────────────────

/**
 * Copy tangolint.py and tangolint_rules.py from the extension bundle into
 * globalStorage so they are reachable by the Python subprocess in any install
 * context (local, remote SSH, vscode-server, devcontainer, etc.).
 *
 * @param {vscode.ExtensionContext} context
 * @returns {Promise<string>} path to the deployed tangolint.py
 */
async function deployScripts(context) {
    const storageDir = context.globalStorageUri.fsPath;
    await fs.promises.mkdir(storageDir, { recursive: true });

    for (const script of ['tangolint.py', 'tangolint_rules.py']) {
        const src = path.join(context.extensionPath, script);
        const dst = path.join(storageDir, script);
        await fs.promises.copyFile(src, dst);
    }

    return path.join(storageDir, 'tangolint.py');
}

// ── Activation / deactivation ─────────────────────────────────────────────────

/**
 * Called by VS Code when the extension is first activated
 * (i.e. when a Python file is opened).
 *
 * @param {vscode.ExtensionContext} context
 */
async function activate(context) {
    // Deploy bundled scripts to globalStorage so they are always reachable.
    try {
        deployedLinterPath = await deployScripts(context);
    } catch (err) {
        vscode.window.showErrorMessage(`TangoLint: failed to deploy scripts — ${err.message}`);
        return;
    }

    diagnosticCollection = vscode.languages.createDiagnosticCollection('tangolint');

    statusBarItem = vscode.window.createStatusBarItem(
        vscode.StatusBarAlignment.Left, 100
    );
    statusBarItem.command = 'workbench.action.problems.focus';

    context.subscriptions.push(diagnosticCollection, statusBarItem);

    // ── Event subscriptions ────────────────────────────────────────────────

    const cfg = () => vscode.workspace.getConfiguration('tangolint');

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
        vscode.commands.registerCommand('tangolint.lintFile', () => {
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
