#!/usr/bin/env node
// Run after `npm ci` in frontend: node scripts/check-api-contract.mjs [Prism base URL].
// Uses the validation libraries already pinned by openapi-typescript in package-lock.json.
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { createRequire } from 'node:module';
import { fileURLToPath } from 'node:url';

const root = new URL('../', import.meta.url);
const require = createRequire(new URL('frontend/package.json', root));
const yaml = require('js-yaml');
const { createConfig, lint } = require('@redocly/openapi-core');
const Ajv = require('@redocly/ajv/dist/2020.js').default;
const filename = fileURLToPath(new URL('docs/openapi.yaml', root));
const spec = yaml.load(readFileSync(filename, 'utf8'));
const failures = [];
const check = (condition, message) => { if (!condition) failures.push(message); };
const methods = new Set(['get', 'post', 'put', 'patch', 'delete', 'options', 'head']);

function dereference(value) {
  const seen = new Set();
  while (value?.$ref) {
    assert(value.$ref.startsWith('#/'), `Only local references are expected: ${value.$ref}`);
    assert(!seen.has(value.$ref), `Circular object reference: ${value.$ref}`);
    seen.add(value.$ref);
    value = value.$ref.slice(2).split('/').reduce((node, part) =>
      node?.[part.replace(/~1/g, '/').replace(/~0/g, '~')], spec);
    assert(value, 'Unresolved local reference');
  }
  return value;
}

function examples(object) {
  if (object.example !== undefined) return [object.example];
  return Object.values(object.examples || {}).map(dereference)
    .filter((example) => example.value !== undefined).map((example) => example.value);
}

const config = await createConfig({ extends: ['minimal'] });
const lintProblems = await lint({ ref: filename, config });
for (const problem of lintProblems) {
      if (problem.severity === 'error') failures.push(`OpenAPI ${problem.ruleId}: ${problem.message} ${JSON.stringify(problem.location?.map((location) => location.pointer))}`);
}
console.log(`OpenAPI lint: ${lintProblems.filter((p) => p.severity === 'error').length} errors, ${lintProblems.filter((p) => p.severity === 'warn').length} warnings`);

const ajv = new Ajv({ strict: false, allErrors: true, validateFormats: true });
ajv.addFormat('uuid', /^[0-9a-f]{8}-(?:[0-9a-f]{4}-){3}[0-9a-f]{12}$/i);
ajv.addFormat('date', { type: 'string', validate: (s) => /^\d{4}-\d{2}-\d{2}$/.test(s) && !Number.isNaN(Date.parse(s)) });
ajv.addFormat('date-time', { type: 'string', validate: (s) => /^\d{4}-\d{2}-\d{2}T/.test(s) && !Number.isNaN(Date.parse(s)) });
ajv.addFormat('email', /^[^\s@]+@[^\s@]+\.[^\s@]+$/);
ajv.addFormat('uri', { type: 'string', validate: (s) => { try { new URL(s); return true; } catch { return false; } } });
// Binary/string formats are annotations; schema shape and MIME are checked separately.
ajv.addFormat('binary', true);
ajv.addFormat('byte', true);
ajv.addSchema({ $id: 'urn:nmh:components', components: spec.components });
let exampleCount = 0;
function validator(schema) {
  // Relative component references must resolve against the shared contract document.
  return ajv.compile({ ...schema, components: spec.components });
}
function validateExample(schema, value, label) {
  try {
    const validate = validator(schema);
    check(validate(value), `${label}: ${ajv.errorsText(validate.errors, { separator: '; ' })}`);
    exampleCount++;
  } catch (error) { failures.push(`${label}: ${error.message}`); }
}

const operations = [];
for (const [path, pathItem] of Object.entries(spec.paths || {})) {
  for (const [method, operation] of Object.entries(pathItem)) {
    if (!methods.has(method)) continue;
    const label = `${method.toUpperCase()} ${path}`;
    operations.push({ path, method, operation, pathItem, label });
    const request = dereference(operation.requestBody);
    for (const [mime, media] of Object.entries(request?.content || {})) {
      const values = examples(media);
      check(values.length > 0, `${label}: missing request example for ${mime}`);
      for (const value of values) validateExample(media.schema, value, `${label} request ${mime}`);
    }
    const success = Object.entries(operation.responses || {}).filter(([code]) => /^2\d\d$/.test(code));
    check(success.length > 0, `${label}: missing successful response`);
    for (const [code, reference] of Object.entries(operation.responses || {})) {
      const response = dereference(reference);
      for (const [mime, media] of Object.entries(response.content || {})) {
        const values = examples(media);
        // OpenAPI represents raw file bodies with a binary schema. A JSON/base64
        // string would misrepresent the actual PNG/JPEG bytes sent by the API.
        const binary = dereference(media.schema)?.format === 'binary';
        check(binary || values.length > 0, `${label}: missing ${code} response example for ${mime}`);
        for (const value of values) validateExample(media.schema, value, `${label} response ${code} ${mime}`);
      }
    }
    if (!['/api/health', '/api/ready'].includes(path)) {
      for (const code of ['400', '401', '403', '404', '409']) {
        check(operation.responses?.[code], `${label}: missing ${code} error contract`);
      }
      check((operation.security ?? spec.security)?.length > 0, `${label}: missing session requirement`);
    }
  }
}
for (const [name, schema] of Object.entries(spec.components?.schemas || {})) {
  if (schema.example !== undefined) validateExample(schema, schema.example, `schema ${name}`);
}

const expected = [
  'POST /api/cases', 'GET /api/cases', 'GET /api/cases/{id}',
  'GET /api/cases/{id}/messages', 'POST /api/cases/{id}/messages',
  'POST /api/cases/{id}/documents', 'GET /api/cases/{id}/documents/{docId}/content',
  'GET /api/cases/{id}/card', 'PATCH /api/cases/{id}/card/facts/{key}', 'POST /api/cases/{id}/card/confirm',
  'GET /api/cases/{id}/company', 'GET /api/cases/{id}/paths', 'POST /api/cases/{id}/path', 'GET /api/cases/{id}/plan',
  'POST /api/cases/{id}/claim', 'GET /api/cases/{id}/claim', 'PUT /api/cases/{id}/claim/personal-data',
  'POST /api/cases/{id}/claim/submit', 'POST /api/cases/{id}/claim/accept-edits', 'POST /api/cases/{id}/claim/reject-edits',
  'POST /api/cases/{id}/claim/mark-sent', 'POST /api/cases/{id}/claim/outcome',
  'GET /api/lawyer/claims', 'POST /api/lawyer/claims/{id}/take', 'GET /api/lawyer/claims/{id}',
  'POST /api/lawyer/claims/{id}/approve', 'POST /api/lawyer/claims/{id}/edit',
  'POST /api/cases/{id}/pool', 'GET /api/lawyer/pool', 'GET /api/lawyer/pool/{id}',
  'POST /api/lawyer/pool/{id}/offers', 'GET /api/cases/{id}/offers', 'POST /api/cases/{id}/offers/{offerId}/accept',
  'GET /api/lawyer/cases', 'GET /api/lawyer/cases/{id}', 'POST /api/lawyer/cases/{id}/submit-work',
  'POST /api/cases/{id}/work/accept', 'POST /api/cases/{id}/close', 'POST /api/lawyer/cases/{id}/start',
  'GET /api/health', 'GET /api/ready',
];
const actual = new Set(operations.map((op) => op.label));
for (const [code, reference] of Object.entries(spec.paths['/api/ready'].get.responses)) {
  const media = dereference(reference).content?.['application/json'];
  for (const example of examples(media || {})) {
    const ready = example.checks?.database === true && example.checks?.redis === true;
    check(code === '200' ? ready && example.status === 'ready' : !ready && example.status === 'not_ready', `Readiness ${code} example contradicts dependency checks`);
  }
}
for (const label of expected) check(actual.has(label), `Missing required operation: ${label}`);
check(new Set(operations.map((op) => op.operation.operationId)).size === operations.length, 'operationIds must be unique');
const statesText = readFileSync(new URL('docs/state-machine.md', root), 'utf8');
const expectedStates = new Set([...statesText.matchAll(/`([a-z][a-z_]+)`/g)].map((match) => match[1]));
const actualStates = new Set(spec.components?.schemas?.CaseState?.enum || []);
check(expectedStates.size === actualStates.size && [...expectedStates].every((s) => actualStates.has(s)), 'CaseState must match the state-machine exactly');

const forbiddenPublicFields = /^(?:owner(?:_id)?|user(?:_id)?|case_id|full_name|phone|email|address|reply_address|contract_reference|personal_data|contact(?:s)?|documents?|document_id|download_url|source_quote|safe_source_quote|facts?|claim|claim_text|template_text|messages?|metadata|rating|lawyer_rating)$/i;
function checkPublicSchema(schema, label, seen = new Set()) {
  if (schema?.$ref) {
    if (seen.has(schema.$ref)) return;
    seen.add(schema.$ref);
  }
  schema = dereference(schema);
  if (!schema || typeof schema !== 'object') return;
  if (schema.type === 'object' || schema.properties) {
    check(schema.additionalProperties === false, `${label}: public objects must have closed properties`);
    for (const [name, property] of Object.entries(schema.properties || {})) {
      check(!forbiddenPublicFields.test(name), `${label}: forbidden public field ${name}`);
      checkPublicSchema(property, `${label}.${name}`, new Set(seen));
    }
  }
  if (schema.items) checkPublicSchema(schema.items, `${label}[]`, new Set(seen));
  for (const keyword of ['allOf', 'anyOf', 'oneOf']) {
    for (const child of schema[keyword] || []) checkPublicSchema(child, label, new Set(seen));
  }
}
for (const name of ['ReviewQueueItem', 'PoolCard']) {
  check(!!spec.components?.schemas?.[name], `Missing privacy-specific schema ${name}`);
  checkPublicSchema(spec.components?.schemas?.[name], name);
}
for (const path of ['/api/lawyer/claims', '/api/lawyer/pool', '/api/lawyer/pool/{id}']) {
  const response = dereference(spec.paths?.[path]?.get?.responses?.['200']);
  for (const media of Object.values(response?.content || {})) checkPublicSchema(media.schema, `GET ${path} response`);
}
function inspectReviewer(schema, seen = new Set()) {
  if (schema?.$ref) {
    check(!/\/(?:Claim|ClaimVersion|ClaimPersonalData|Fact|Card|DocumentMetadata)$/.test(schema.$ref), `Reviewer reuses private schema ${schema.$ref}`);
    if (seen.has(schema.$ref)) return;
    seen.add(schema.$ref);
  }
  schema = dereference(schema);
  if (!schema || typeof schema !== 'object') return;
  for (const [name, property] of Object.entries(schema.properties || {})) {
    check(!/^(?:full_name|phone|email|address|reply_address|contract_reference|personal_data|owner_id|filename|source_quote|download_url)$/.test(name), `Reviewer schema contains private field ${name}`);
    inspectReviewer(property, new Set(seen));
  }
  if (schema.items) inspectReviewer(schema.items, new Set(seen));
  for (const keyword of ['allOf', 'anyOf', 'oneOf']) for (const child of schema[keyword] || []) inspectReviewer(child, new Set(seen));
}
inspectReviewer(spec.components?.schemas?.ReviewClaim);
// Reject representative invalid inputs rather than accepting every happy fixture.
check(!validator(spec.components.schemas.MoneyKopecks)(1.5), 'Money schema must reject fractional kopecks');
check(!validator(spec.components.schemas.ConsentInput)({ accepted: false, text_version: 'demo-v1' }), 'Consent schema must reject accepted=false');
check(!validator(spec.components.schemas.Fact)({ key: 'company_name', value: null, status: 'found', source: null, source_quote: null, required: true }), 'Fact schema must reject found without value/source');
for (const { label, operation } of operations) {
  const body = dereference(operation.requestBody);
  for (const [mime, media] of Object.entries(body?.content || {})) {
    if (!mime.includes('json')) continue;
    const example = examples(media)[0];
    for (const field of ['owner_id', 'role', 'paid', 'state']) {
      check(!validator(media.schema)({ ...example, [field]: field === 'paid' ? true : 'attacker' }), `${label}: schema accepts client-controlled ${field}`);
    }
  }
}

// Examples are the frontend's initial fixture, so validate domain meaning too.
const transitionExamples = new Map([
  ['POST /api/cases/{id}/card/confirm', 'card_confirmed'],
  ['POST /api/cases/{id}/claim/submit', 'claim_in_review'],
  ['POST /api/cases/{id}/claim/accept-edits', 'claim_approved'],
  ['POST /api/cases/{id}/claim/reject-edits', 'claim_in_review'],
  ['POST /api/cases/{id}/claim/mark-sent', 'awaiting_response'],
  ['POST /api/lawyer/claims/{id}/approve', 'claim_approved'],
  ['POST /api/lawyer/claims/{id}/edit', 'claim_edited'],
  ['POST /api/cases/{id}/offers/{offerId}/accept', 'offer_accepted'],
  ['POST /api/lawyer/cases/{id}/start', 'in_progress'],
  ['POST /api/lawyer/cases/{id}/submit-work', 'work_submitted'],
  ['POST /api/cases/{id}/work/accept', 'completed'],
  ['POST /api/cases/{id}/close', 'closed'],
]);
function walkExample(value, visit) {
  if (!value || typeof value !== 'object') return;
  visit(value);
  for (const child of Object.values(value)) {
    if (Array.isArray(child)) child.forEach((item) => walkExample(item, visit));
    else walkExample(child, visit);
  }
}
for (const { label, path, method, operation } of operations) {
  for (const [code, reference] of Object.entries(operation.responses)) {
    if (!/^2\d\d$/.test(code)) continue;
    for (const media of Object.values(dereference(reference).content || {})) {
      for (const value of examples(media)) {
        const state = value?.case?.state ?? value?.state;
        if (transitionExamples.has(label)) check(state === transitionExamples.get(label), `${label}: example must reflect ${transitionExamples.get(label)} transition, received ${state}`);
        if (method === 'post' && ['/api/cases', '/api/cases/{id}/messages', '/api/cases/{id}/claim'].includes(path)) {
          check((value.case?.ai_state ?? value.ai_state) === 'thinking', `${label}: async acceptance example must show ai_state=thinking`);
        }
        if (label === 'GET /api/cases/{id}/paths') {
          const options = value.items || [];
          check(new Set(options.map((option) => option.path)).size === 3, 'Paths example must include all three choices');
          check(options.find((option) => option.path === 'self_guided')?.price_kopecks === 0, 'Self-guided path example must be free');
        }
        if (label === 'GET /api/lawyer/cases/{id}') {
          check(value.accepted_offer?.accepted === true, 'Assigned lawyer example must contain an accepted offer');
          check(['offer_accepted', 'in_progress', 'work_submitted'].includes(state), 'Assigned lawyer example must have an active assignment state');
        }
        walkExample(value, (object) => {
          if (object.status === 'found' && 'source_quote' in object) {
            check(typeof object.value === 'string' && object.value.length > 0 && object.source && object.source_quote, `${label}: found fact example requires value and source quote`);
          }
          if (object.status === 'not_found' && 'source_quote' in object) {
            check(object.value === null && object.source === null && object.source_quote === null, `${label}: not_found fact must not invent a value/source`);
          }
        });
      }
    }
  }
}
console.log(`Contract coverage: ${operations.length} operations, ${actualStates.size} case states, ${exampleCount} examples; public DTOs inspected`);

const base = process.argv[2];
if (base && failures.length === 0) {
  let ready = false;
  for (let attempt = 0; attempt < 20 && !ready; attempt++) {
    try { ready = (await fetch(new URL('/api/health', base), { signal: AbortSignal.timeout(2000) })).ok; }
    catch { /* The newly started mock may still be loading the contract. */ }
    if (!ready) await new Promise((resolve) => setTimeout(resolve, 500));
  }
  assert(ready, 'Prism did not become ready');
  for (const entry of operations) {
    const { operation, pathItem, method, label } = entry;
    let path = entry.path;
    const parameters = [...(pathItem.parameters || []), ...(operation.parameters || [])].map(dereference);
    for (const parameter of parameters) {
      if (parameter.in === 'path') {
        const value = parameter.example ?? parameter.schema?.example ?? dereference(parameter.schema)?.example;
        assert(value !== undefined, `${label}: path parameter ${parameter.name} needs an example`);
        path = path.replace(`{${parameter.name}}`, encodeURIComponent(value));
      }
    }
    const url = new URL(path, base);
    const headers = { cookie: 'sessionid=contract-mock', 'X-CSRFToken': 'contract-mock' };
    for (const parameter of parameters.filter((p) => p.required && p.in !== 'path')) {
      const value = parameter.example ?? dereference(parameter.schema)?.example;
      assert(value !== undefined, `${label}: required parameter ${parameter.name} needs an example`);
      if (parameter.in === 'query') url.searchParams.set(parameter.name, value);
      if (parameter.in === 'header') headers[parameter.name] = String(value);
    }
    const [status, reference] = Object.entries(operation.responses).find(([code]) => /^2\d\d$/.test(code));
    headers.prefer = `code=${status}`;
    const responseSchema = dereference(reference);
    const responseMime = Object.keys(responseSchema.content || {})[0];
    if (responseMime) headers.accept = responseMime;
    const request = dereference(operation.requestBody);
    let body;
    if (request?.content) {
      const [mime, media] = Object.entries(request.content)[0];
      const value = examples(media)[0];
      if (mime === 'multipart/form-data') {
        body = new FormData();
        for (const [key, item] of Object.entries(value)) {
          const property = dereference(media.schema)?.properties?.[key];
          if (property?.format === 'binary') body.append(key, new Blob([String(item)], { type: 'text/plain' }), 'demo.txt');
          else body.append(key, typeof item === 'object' ? JSON.stringify(item) : String(item));
        }
      } else {
        headers['content-type'] = mime;
        body = mime.includes('json') ? JSON.stringify(value) : String(value);
      }
    }
    try {
      const response = await fetch(url, { method: method.toUpperCase(), headers, body, signal: AbortSignal.timeout(20000) });
      const text = await response.text();
      check(String(response.status) === status, `${label}: Prism returned ${response.status}, expected ${status}: ${text.slice(0, 200)}`);
      const media = responseSchema.content?.[responseMime];
      if (media && String(response.status) === status) validateExample(media.schema, responseMime.includes('json') ? JSON.parse(text) : text, `${label} Prism`);
      console.log(`${label} -> ${response.status}`);
    } catch (error) { failures.push(`${label}: ${error.message}`); }
  }
}
if (failures.length) {
  for (const failure of failures) console.error(`FAIL: ${failure}`);
  process.exitCode = 1;
} else console.log(`PASS: contract${base ? ' and all Prism responses' : ''} validated`);
