// bun scripts/serve.mjs <dir> [port]: serves a built site the way a static host does (/x -> /x/index.html).
import { serve } from './_host.mjs'

const host = serve(process.argv[2], Number(process.argv[3] ?? 4173))
console.log(`serving ${process.argv[2]} on ${host.origin}`)
