#!/usr/bin/env node
/**
 * Fetch OpenAPI schema from running backend and write a type reference stub.
 * Full codegen: install openapi-typescript and extend this script.
 *
 * Usage: OPENAPI_URL=http://127.0.0.1:8000/openapi.json node scripts/generate-api-types.mjs
 */
import { writeFileSync } from 'node:fs'
import { resolve, dirname } from 'node:path'
import { fileURLToPath } from 'node:url'

const __dirname = dirname(fileURLToPath(import.meta.url))
const url = process.env.OPENAPI_URL || 'http://127.0.0.1:8000/openapi.json'

const res = await fetch(url)
if (!res.ok) {
  console.error(`Failed to fetch OpenAPI schema from ${url}: ${res.status}`)
  process.exit(1)
}
const schema = await res.json()
const out = resolve(__dirname, '../src/types/openapi.snapshot.json')
writeFileSync(out, JSON.stringify(schema, null, 2))
console.log(`Wrote OpenAPI snapshot to ${out}`)
console.log('Manual types live in src/types/api.ts — diff against snapshot when schemas change.')
