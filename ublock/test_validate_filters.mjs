import assert from 'node:assert/strict';
import { mkdtemp, writeFile, mkdir, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join, dirname } from 'node:path';
import { test } from 'node:test';
import { loadParser, validateText } from './validate_filters.mjs';

const parser = loadParser({
    cache: process.env.UBO_PARSER_CACHE,
    offline: process.env.UBO_PARSER_OFFLINE === '1',
});

test('official parser accepts targeted cosmetics and rejects misspelled ABP operator', async () => {
    const { module } = await parser;
    assert.equal(validateText('example.com##.newsletter\n', module).issues.length, 0);
    const selector = 'tumblr.com#?#[style="background-color: rgb(124, 92, 255); color: rgb(255, 255, 255);"]';
    assert.equal(validateText(`${selector}:abp-contains(Join over 100 million people)`, module).issues.length, 1);
    assert.equal(validateText(`${selector}:has-text(Join over 100 million people)`, module).issues.length, 0);
});

test('ignored generic scriptlets fail while hostname-specific scriptlets pass', async () => {
    const { module } = await parser;
    const report = validateText('##+js(ra, class, div.wkwp-paywall, stay)\nexample.com##+js(ra, class, div.wkwp-paywall, stay)', module);
    assert.equal(report.issues.length, 1);
    assert.equal(report.issues[0].line, 1);
    assert.match(report.issues[0].message, /Generic scriptlet/);
});

test('official preprocessor conditions preserve original line numbers', async () => {
    const { module } = await parser;
    const report = validateText('!#if adguard_app_ios\nexample.com##[\n!#else\nexample.com##.newsletter\n!#endif\nexample.com##[\n', module);
    assert.equal(report.entries, 3);
    assert.equal(report.enabled, 2);
    assert.equal(report.skipped, 1);
    assert.equal(report.issues.length, 1);
    assert.equal(report.issues[0].line, 6);
});

test('malformed conditional structure cannot produce a clean result', async () => {
    const { module } = await parser;
    assert.equal(validateText('!#else\n!#endif\n!#if false\n!#else\n!#else\n', module).issues.length, 4);
});

test('offline mode rejects missing or corrupted cached source before importing', async () => {
    const root = await mkdtemp(join(tmpdir(), 'ubo-parser-test-'));
    try {
        await assert.rejects(loadParser({ cache: root, offline: true }), /Missing cached parser/);
        const target = join(root, 'src/js/static-filtering-parser.js');
        await mkdir(dirname(target), { recursive: true });
        await writeFile(target, '// corrupted\n');
        await assert.rejects(loadParser({ cache: root, offline: true }), /checksum mismatch/);
    } finally {
        await rm(root, { recursive: true, force: true });
    }
});

test('download HTTP errors and checksum mismatches fail without importing data', async () => {
    await parser;
    const root = await mkdtemp(join(tmpdir(), 'ubo-parser-download-test-'));
    const originalFetch = globalThis.fetch;
    try {
        globalThis.fetch = async () => new Response('unavailable', { status: 503 });
        await assert.rejects(loadParser({ cache: root }), /download failed \(503\)/);
        globalThis.fetch = async () => new Response('// unexpected source\n', { status: 200 });
        await assert.rejects(loadParser({ cache: root }), /Downloaded parser checksum mismatch/);
    } finally {
        globalThis.fetch = originalFetch;
        await rm(root, { recursive: true, force: true });
    }
});
