import fs from 'node:fs/promises'
import openapiTS, { astToString } from 'openapi-typescript'
const source = new URL('../../docs/api/backend.runtime.openapi.json', import.meta.url)
const schema = JSON.parse(await fs.readFile(source, 'utf8'))
const types = astToString(await openapiTS(schema))
const routes = Object.entries(schema.paths).flatMap(([path, operations]) =>
  Object.keys(operations)
    .filter((method) => ['get', 'post', 'patch'].includes(method) && !path.startsWith('/internal/'))
    .map((method) => [method.toUpperCase(), path]),
)
const files = [
  [new URL('../app/types/backend.d.ts', import.meta.url), types],
  [
    new URL('../server/utils/backend-routes.ts', import.meta.url),
    '// Generated from the backend runtime OpenAPI; do not edit.\nexport const backendRoutes = ' +
      JSON.stringify(routes, null, 2) +
      ' as const\n',
  ],
]
for (const [file, content] of files) {
  if (process.argv.includes('--check')) {
    if ((await fs.readFile(file, 'utf8')) !== content)
      throw Error('API contract drift: ' + file.pathname)
  } else await fs.writeFile(file, content)
}
console.log('Backend types and public route allowlist are current.')
