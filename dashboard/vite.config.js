import { defineConfig } from 'vite'
import { svelte } from '@sveltejs/vite-plugin-svelte'
import fs from 'node:fs/promises'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const __dirname = path.dirname(fileURLToPath(import.meta.url))

// 선택적 LLM 호출 워크플로우가 <repo root>/outputs/에 세션을 쓴다(io_utils/session.py의
// OUTPUTS_DIR). 대시보드는 사용자가 폴더를 선택하지 않고 이 고정 경로만 읽는다.
const OUTPUTS_DIR = path.resolve(__dirname, '..', 'outputs')

// session_id는 URL 경로 세그먼트에서 오므로, outputs/ 밖으로 벗어나는 경로
// (.. 포함, 슬래시 포함)는 세션 폴더 이름일 수 없다고 보고 거부한다.
function isSafeSessionId(id) {
  return typeof id === 'string' && id.length > 0 && !id.includes('/') && !id.includes('..')
}

async function readJsonIfExists(filePath) {
  try {
    return JSON.parse(await fs.readFile(filePath, 'utf-8'))
  } catch (e) {
    if (e.code === 'ENOENT') return null
    throw e
  }
}

function sendJson(res, status, body) {
  res.statusCode = status
  res.setHeader('Content-Type', 'application/json; charset=utf-8')
  res.end(JSON.stringify(body))
}

// outputs-api: 백엔드 없이 브라우저에서 파일시스템 권한을 요청하던 방식(File
// System Access API) 대신, Vite dev 서버가 고정 루트(outputs/)를 직접 읽어
// /api/sessions*로 내려준다. vite dev에서만 동작한다 — configureServer는
// `npm run build`/`vite preview`에는 적용되지 않는다.
function outputsApiPlugin() {
  return {
    name: 'outputs-api',
    configureServer(server) {
      server.middlewares.use('/api/sessions', async (req, res, next) => {
        try {
          const url = new URL(req.url, 'http://localhost')
          const parts = url.pathname.split('/').filter(Boolean) // ["", "id", "meta"|"results"]

          // GET /api/sessions  → 세션 목록
          if (parts.length === 0) {
            let dirents
            try {
              dirents = await fs.readdir(OUTPUTS_DIR, { withFileTypes: true })
            } catch (e) {
              if (e.code === 'ENOENT') return sendJson(res, 200, [])
              throw e
            }
            const sessions = []
            for (const d of dirents) {
              if (!d.isDirectory()) continue
              const meta = await readJsonIfExists(path.join(OUTPUTS_DIR, d.name, 'session.json'))
              if (meta) sessions.push(meta)
            }
            sessions.sort((a, b) => String(b.session_id).localeCompare(String(a.session_id)))
            return sendJson(res, 200, sessions)
          }

          const [sessionId, sub] = parts
          if (!isSafeSessionId(sessionId)) {
            return sendJson(res, 400, { error: 'invalid session id' })
          }
          const sessionDir = path.join(OUTPUTS_DIR, sessionId)

          // GET /api/sessions/:id/meta  → session.json + results.jsonl mtime
          if (sub === 'meta') {
            const meta = await readJsonIfExists(path.join(sessionDir, 'session.json'))
            if (!meta) return sendJson(res, 404, { error: 'session not found' })
            let results_mtime_ms = null
            try {
              results_mtime_ms = (await fs.stat(path.join(sessionDir, 'results.jsonl'))).mtimeMs
            } catch (e) {
              if (e.code !== 'ENOENT') throw e
            }
            return sendJson(res, 200, { ...meta, results_mtime_ms })
          }

          // GET /api/sessions/:id/results  → results.jsonl 원문(줄 단위 JSON)
          if (sub === 'results') {
            let text
            try {
              text = await fs.readFile(path.join(sessionDir, 'results.jsonl'), 'utf-8')
            } catch (e) {
              if (e.code === 'ENOENT') return sendJson(res, 404, { error: 'results not found' })
              throw e
            }
            res.statusCode = 200
            res.setHeader('Content-Type', 'application/x-ndjson; charset=utf-8')
            return res.end(text)
          }

          return next()
        } catch (e) {
          sendJson(res, 500, { error: String(e && e.message || e) })
        }
      })
    },
  }
}

// https://vite.dev/config/
export default defineConfig({
  plugins: [svelte(), outputsApiPlugin()],
})
