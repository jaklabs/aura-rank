#!/usr/bin/env node
'use strict'

/*
 * npx wrapper for aura-rank.
 *
 * The analyzer is Python -- this exists so JavaScript and TypeScript developers,
 * who are a large part of who the tool is for, can run it without a clone. It
 * shells out to the real scanner and adds nothing of its own.
 *
 * It is deliberately not a stub published to hold a name. npm removes those, and
 * it would be a poor thing to do on a project whose pitch is honesty.
 */

const { spawn, spawnSync } = require('node:child_process')

const PIP_HINT = [
  'aura-rank is not installed.',
  '',
  '  pip install aura-rank',
  '',
  'Or run it from a clone with nothing installed at all:',
  '',
  '  git clone https://github.com/jaklabs/aura-rank && cd aura-rank',
  '  python3 -m aurarank.scan ~/code/your-project',
].join('\n')

function findPython() {
  for (const candidate of ['python3', 'python']) {
    const probe = spawnSync(candidate, ['-c', 'import sys; sys.exit(0 if sys.version_info >= (3, 9) else 1)'])
    if (probe.status === 0) return candidate
  }
  return null
}

const python = findPython()
if (!python) {
  console.error('aurarank needs Python 3.9 or newer on PATH.\nhttps://www.python.org/downloads/')
  process.exit(1)
}

const args = process.argv.slice(2)
const command = args[0] === 'portfolio' ? 'portfolio' : 'scan'
const rest = args[0] === 'scan' || args[0] === 'portfolio' ? args.slice(1) : args

const installed = spawnSync(python, ['-c', 'import aurarank'])
if (installed.status !== 0) {
  console.error(PIP_HINT)
  process.exit(1)
}

const child = spawn(python, ['-m', `aurarank.${command}`, ...rest], { stdio: 'inherit' })
child.on('exit', (code) => process.exit(code ?? 0))
