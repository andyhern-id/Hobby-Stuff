#!/usr/bin/env node
/** Validate subscription syntax with a checksum-pinned official uBlock parser.
 *
 * Requires Node 20+. First run downloads four pinned upstream modules to a cache.
 * This checks syntax and known ignored generic rules, not live-page behavior or
 * whether scriptlet names/arguments work as intended at runtime.
 */

import { createHash } from 'node:crypto';
import { readFile, writeFile, mkdir, rename, unlink } from 'node:fs/promises';
import { dirname, isAbsolute, resolve, sep } from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';

const HERE = dirname(fileURLToPath(import.meta.url));
const DEFAULT_FILES = [
    'ubo-no-bullshit-supplement.txt',
    'ubo-no-bullshit-paywalls.txt',
    'ubo-no-bullshit-interface.txt',
].map(name => resolve(HERE, name));
const PROFILES = {
    firefox: ['ublock', 'firefox', 'html_filtering', 'ipaddress'],
    chromium: ['ublock', 'chromium'],
};
const PARSER_FILES = [
    'src/js/static-filtering-parser.js',
    'src/js/arglist-parser.js',
    'src/js/jsonpath.js',
    'src/lib/csstree/css-tree.js',
];

export function sha256(bytes) {
    return createHash('sha256').update(bytes).digest('hex');
}

export async function loadParser({ cache, offline = false, lockPath = resolve(HERE, 'parser-lock.json') } = {}) {
    const lock = JSON.parse(await readFile(lockPath, 'utf8'));
    if (lock.repository !== 'gorhill/uBlock' || !/^[a-f0-9]{40}$/.test(lock.commit)) {
        throw new Error('Invalid parser lock: expected official repository and a full commit SHA');
    }
    if (!lock.files || Object.keys(lock.files).sort().join('\n') !== PARSER_FILES.slice().sort().join('\n')) {
        throw new Error('Invalid parser lock: all four parser dependencies must be checksum-pinned');
    }
    const cacheRoot = resolve(cache || resolve(HERE, '..', '.cache', 'ublock-parser', lock.commit));
    for (const [path, expected] of Object.entries(lock.files)) {
        const target = resolve(cacheRoot, path);
        if (isAbsolute(path) || !target.startsWith(cacheRoot + sep) || !/^[a-f0-9]{64}$/.test(expected)) {
            throw new Error(`Invalid parser lock entry: ${path}`);
        }
        let bytes;
        try {
            bytes = await readFile(target);
        } catch (error) {
            if (error.code !== 'ENOENT') throw error;
            if (offline) throw new Error(`Missing cached parser module in offline mode: ${target}`);
            const url = `https://raw.githubusercontent.com/${lock.repository}/${lock.commit}/${path}`;
            const response = await fetch(url, { signal: AbortSignal.timeout(30_000) });
            if (!response.ok) throw new Error(`Parser download failed (${response.status}): ${url}`);
            bytes = Buffer.from(await response.arrayBuffer());
            if (sha256(bytes) !== expected) throw new Error(`Downloaded parser checksum mismatch: ${path}`);
            await mkdir(dirname(target), { recursive: true });
            const temporary = `${target}.${process.pid}.tmp`;
            try {
                await writeFile(temporary, bytes);
                await rename(temporary, target);
            } finally {
                await unlink(temporary).catch(error => { if (error.code !== 'ENOENT') throw error; });
            }
        }
        if (sha256(bytes) !== expected) {
            throw new Error(`Cached parser checksum mismatch: ${target}; remove the cache and retry`);
        }
    }
    // Upstream modules use ESM syntax despite the .js extension.
    await writeFile(resolve(cacheRoot, 'package.json'), '{"type":"module"}\n');
    const module = await import(pathToFileURL(resolve(cacheRoot, 'src/js/static-filtering-parser.js')).href);
    return { module, commit: lock.commit };
}

function isEntry(line) {
    return line !== '' && !line.startsWith('!') && !/^\[Adblock[^\]]*\]$/i.test(line);
}

export function validateText(content, module, { environment = 'firefox', name = '<input>' } = {}) {
    const profile = PROFILES[environment];
    if (!profile) throw new Error(`Unknown environment: ${environment}`);
    const parser = new module.AstFilterParser({
        interactive: true,
        nativeCssHas: true,
        trustedSource: false,
        canFilterResponseBody: environment === 'firefox',
    });
    const report = { file: name, environment, entries: 0, enabled: 0, skipped: 0, issues: [] };
    const stack = [];
    const enabled = () => stack.every(frame => frame.active);
    const addIssue = (line, message, rule) => report.issues.push({ line, message, rule });
    for (const [offset, raw] of content.split(/\r?\n/).entries()) {
        const line = raw.trim();
        const number = offset + 1;
        const directive = /^!#(if|else|endif)\b\s*(.*)$/.exec(line);
        if (directive) {
            const [, action, expression] = directive;
            if (action === 'if') {
                const result = module.utils.preparser.evaluateExpr(expression, profile);
                if (result === undefined) addIssue(number, 'Unknown or invalid preprocessor condition', line);
                stack.push({ line: number, active: result !== false, alternative: false });
            } else if (action === 'else') {
                const frame = stack.at(-1);
                if (!frame) addIssue(number, '!#else without !#if', line);
                else if (frame.alternative) addIssue(number, 'Duplicate !#else', line);
                else {
                    frame.alternative = true;
                    frame.active = !frame.active;
                }
            } else if (!stack.pop()) addIssue(number, '!#endif without !#if', line);
            continue;
        }
        if (/^!#include\b/.test(line)) {
            if (enabled()) addIssue(number, 'Includes must be expanded before validating a standalone subscription', line);
            continue;
        }
        if (!isEntry(line)) continue;
        report.entries++;
        if (!enabled()) { report.skipped++; continue; }
        report.enabled++;
        parser.parse(line);
        if (parser.hasError() || parser.isUnsupported() || !parser.isFilter()) {
            addIssue(number, parser.result.error || 'Rejected by the pinned uBlock parser', line);
        } else if (parser.isScriptletFilter() && !parser.isException() && /^#/.test(line)) {
            addIssue(number, 'Generic scriptlet filters are ignored by uBlock; specify hostnames', line);
        } else if (parser.isCosmeticFilter() && /^##/.test(line) && parser.result.compiled?.includes('"tasks":')) {
            addIssue(number, 'Generic procedural cosmetic filters are ignored by uBlock; specify hostnames', line);
        }
    }
    for (const frame of stack) addIssue(frame.line, 'Unclosed !#if', '');
    return report;
}

export async function main(args = process.argv.slice(2)) {
    const options = { cache: process.env.UBO_PARSER_CACHE, offline: process.env.UBO_PARSER_OFFLINE === '1' };
    let environment = 'firefox';
    let json = false;
    const files = [];
    for (let i = 0; i < args.length; i++) {
        const value = args[i];
        if (value === '--cache' || value === '--env') {
            if (!args[i + 1] || args[i + 1].startsWith('--')) throw new Error(`${value} requires a value`);
            if (value === '--cache') options.cache = args[++i];
            else environment = args[++i];
        } else if (value === '--offline') options.offline = true;
        else if (value === '--json') json = true;
        else if (value === '--help') {
            console.log('Usage: node ublock/validate_filters.mjs [--cache DIR] [--offline] [--env firefox|chromium] [--json] [LIST ...]');
            return 0;
        } else if (value.startsWith('-')) throw new Error(`Unknown argument: ${value}`);
        else files.push(resolve(value));
    }
    if (!PROFILES[environment]) throw new Error(`Unknown environment: ${environment}`);
    const { module, commit } = await loadParser(options);
    const reports = [];
    for (const path of files.length ? files : DEFAULT_FILES) {
        reports.push(validateText(await readFile(path, 'utf8'), module, { environment, name: path }));
    }
    if (json) console.log(JSON.stringify({ parserCommit: commit, reports }, null, 2));
    else {
        console.log(`uBlock parser ${commit} (${environment})`);
        for (const report of reports) {
            console.log(`${report.file}: ${report.entries} entries, ${report.enabled} enabled, ${report.skipped} conditional skips, ${report.issues.length} errors`);
            for (const issue of report.issues) console.error(`  ${report.file}:${issue.line}: ${issue.message}\n    ${issue.rule}`);
        }
    }
    return reports.some(report => report.issues.length > 0) ? 1 : 0;
}

if (process.argv[1] && resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
    main().then(code => { process.exitCode = code; }).catch(error => {
        console.error(`Filter validation failed: ${error.message}`);
        process.exitCode = 2;
    });
}
