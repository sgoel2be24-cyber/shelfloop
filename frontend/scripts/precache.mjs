import { readdir, readFile, writeFile } from 'node:fs/promises'
import { createHash } from 'node:crypto'
const assets = (await readdir(new URL('../dist/assets/', import.meta.url))).filter(n => /\.(js|css|woff2?|svg)$/.test(n)).map(n => '/assets/' + n)
const version = createHash('sha256').update(assets.join('|')).digest('hex').slice(0, 12)
await writeFile(new URL('../dist/precache-manifest.json', import.meta.url), JSON.stringify({version, assets}))
const worker = await readFile(new URL('../public/sw.js', import.meta.url), 'utf8')
await writeFile(new URL('../dist/sw.js', import.meta.url), worker.replace('__BUILD_VERSION__', version))
console.log(`Offline shell prepared: ${assets.length} assets · ${version}`)
