#!/usr/bin/env node

/**
 * Nife MCP Server NPM Entry Point
 * Launches the Python-based MCP server
 */

const { spawn } = require('child_process');
const path = require('path');

// Get Python command (try python3 first, fallback to python)
const pythonCmd = process.platform === 'win32' ? 'python' : 'python3';

// Get the directory where the package is installed
const packageDir = path.join(__dirname, '..');

// Arguments for Python
const args = ['-m', 'nife_mcp_server.intelligent_main'];

// Spawn Python process
const pythonProcess = spawn(pythonCmd, args, {
  cwd: packageDir,
  stdio: 'inherit', // Inherit stdin, stdout, stderr
  env: {
    ...process.env,
    PYTHONUNBUFFERED: '1'
  }
});

// Handle process exit
pythonProcess.on('error', (error) => {
  console.error('Failed to start Nife MCP Server:', error.message);
  console.error('\nMake sure Python 3.8+ is installed and in your PATH.');
  console.error('Try running: python3 --version');
  process.exit(1);
});

pythonProcess.on('exit', (code) => {
  process.exit(code || 0);
});

// Handle Ctrl+C
process.on('SIGINT', () => {
  pythonProcess.kill('SIGINT');
});

process.on('SIGTERM', () => {
  pythonProcess.kill('SIGTERM');
});
