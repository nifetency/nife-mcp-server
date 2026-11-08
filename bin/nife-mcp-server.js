#!/usr/bin/env node

/**
 * Nife MCP Server NPM Entry Point
 * Launches the Python-based MCP server (stdio) from the bundled src/ directory.
 */

const { spawn, spawnSync } = require('child_process');
const path = require('path');

const packageDir = path.join(__dirname, '..');
const srcDir = path.join(packageDir, 'src');
const requirementsFile = path.join(packageDir, 'requirements.txt');

// Python command: $PYTHON, else python (Windows) / python3 (elsewhere)
const pythonCmd =
  process.env.PYTHON || (process.platform === 'win32' ? 'python' : 'python3');

// Make the bundled package importable without a separate pip install.
const sep = path.delimiter;
const pythonPath = process.env.PYTHONPATH
  ? `${srcDir}${sep}${process.env.PYTHONPATH}`
  : srcDir;

function fail(lines) {
  // stdout is the MCP channel, so every message goes to stderr.
  console.error(lines.join('\n'));
  process.exit(1);
}

// Preflight: Python 3.10+ and the runtime dependencies, with an actionable message.
const check = spawnSync(
  pythonCmd,
  [
    '-c',
    'import sys\n' +
      'if sys.version_info < (3, 10):\n' +
      '    sys.exit(2)\n' +
      'import requests\n'
  ],
  { env: { ...process.env, PYTHONPATH: pythonPath }, encoding: 'utf8' }
);

if (check.error) {
  fail([
    `Failed to start Nife MCP Server: could not run "${pythonCmd}" (${check.error.message}).`,
    'Install Python 3.10+ and make sure it is on your PATH, or set the PYTHON environment variable.',
    'Check with: python3 --version'
  ]);
}
if (check.status === 2) {
  fail([
    'Nife MCP Server needs Python 3.10 or newer.',
    `Found an older interpreter at "${pythonCmd}". Install a newer Python or set PYTHON to its path.`
  ]);
}
if (check.status !== 0) {
  fail([
    'Nife MCP Server is missing Python dependencies.',
    `Install them with: ${pythonCmd} -m pip install -r "${requirementsFile}"`,
    'or install the package from PyPI: pip install nife-mcp-server',
    (check.stderr || '').trim()
  ].filter(Boolean));
}

const pythonProcess = spawn(pythonCmd, ['-m', 'nife_mcp_server.intelligent_main'], {
  cwd: packageDir,
  stdio: 'inherit', // stdin/stdout/stderr pass straight through for MCP stdio
  env: {
    ...process.env,
    PYTHONPATH: pythonPath,
    PYTHONUNBUFFERED: '1'
  }
});

pythonProcess.on('error', (error) => {
  fail([`Failed to start Nife MCP Server: ${error.message}`]);
});

pythonProcess.on('exit', (code, signal) => {
  process.exit(code === null ? (signal ? 1 : 0) : code);
});

process.on('SIGINT', () => pythonProcess.kill('SIGINT'));
process.on('SIGTERM', () => pythonProcess.kill('SIGTERM'));
