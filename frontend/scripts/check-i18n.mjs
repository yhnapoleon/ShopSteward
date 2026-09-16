import fs from 'node:fs'
import path from 'node:path'
import { parse } from 'vue/compiler-sfc'
import ts from 'typescript'
const root = new URL('../app/', import.meta.url)
const catalog = JSON.parse(fs.readFileSync(new URL('i18n/en.json', root), 'utf8'))
const han = /[\u3400-\u9fff]/
const failures = []
let files = 0
function checkExpression(code, file) {
  const ast = ts.createSourceFile('expression.ts', code, ts.ScriptTarget.Latest, true)
  function visit(node) {
    if (ts.isStringLiteral(node) || ts.isNoSubstitutionTemplateLiteral(node)) {
      const text = node.text.replace(/\s+/g, ' ').trim()
      if (han.test(text) && !Object.hasOwn(catalog, text))
        failures.push(`${file}: missing catalog entry: ${text}`)
    }
    ts.forEachChild(node, visit)
  }
  visit(ast)
}
function template(node, file) {
  if (node.type === 2 && han.test(node.content))
    failures.push(`${file}: untranslated template text: ${node.content.trim()}`)
  if (node.type === 5) checkExpression(node.content.content, file)
  for (const prop of node.props || []) {
    if (prop.type === 6 && prop.value && han.test(prop.value.content))
      failures.push(`${file}: untranslated attribute ${prop.name}`)
    if (prop.type === 7 && prop.exp) checkExpression(prop.exp.content, file)
  }
  for (const child of node.children || []) template(child, file)
}
for (const dir of ['components', 'pages']) {
  const location = new URL(dir + '/', root)
  for (const name of fs.readdirSync(location)) {
    if (!name.endsWith('.vue')) continue
    const file = path.join(dir, name)
    const { descriptor } = parse(fs.readFileSync(new URL(name, location), 'utf8'))
    template(descriptor.template.ast, file)
    files++
  }
}
for (const [key, value] of Object.entries(catalog)) {
  if (!value.trim()) failures.push(`Empty translation: ${key}`)
  const placeholders = (text) =>
    [...text.matchAll(/\{\d+\}/g)]
      .map((match) => match[0])
      .sort()
      .join(',')
  if (placeholders(key) !== placeholders(value)) failures.push(`Placeholder mismatch: ${key}`)
}
if (failures.length) {
  console.error(failures.join('\n'))
  process.exitCode = 1
} else
  console.log(
    `${files} templates, ${Object.keys(catalog).length} translations: no missing UI strings or mismatched placeholders.`,
  )
