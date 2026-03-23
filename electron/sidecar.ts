import { ChildProcess, spawn } from 'child_process'
import { app } from 'electron'
import path from 'path'

const BACKEND_PORT = 18923
const HEALTH_URL = `http://127.0.0.1:${BACKEND_PORT}/api/health`
const MAX_RETRIES = 30
const RETRY_INTERVAL_MS = 500

let backendProcess: ChildProcess | null = null

function getBackendPath(): { cmd: string; args: string[] } {
  if (app.isPackaged) {
    const exeName =
      process.platform === 'win32' ? 'file-organizer-backend.exe' : 'file-organizer-backend'
    const backendPath = path.join(process.resourcesPath, 'backend', exeName)
    return { cmd: backendPath, args: [] }
  } else {
    return {
      cmd: 'uvicorn',
      args: [
        'server:app',
        '--host', '127.0.0.1',
        '--port', String(BACKEND_PORT),
        '--reload',
      ],
    }
  }
}

async function waitForHealth(): Promise<void> {
  for (let i = 0; i < MAX_RETRIES; i++) {
    try {
      const res = await fetch(HEALTH_URL)
      if (res.ok) return
    } catch {
      // not ready yet
    }
    await new Promise((r) => setTimeout(r, RETRY_INTERVAL_MS))
  }
  throw new Error(`Backend did not become healthy after ${MAX_RETRIES} retries`)
}

export async function startSidecar(): Promise<void> {
  const { cmd, args } = getBackendPath()
  const cwd = app.isPackaged
    ? path.join(process.resourcesPath, 'backend')
    : path.join(__dirname, '..', 'backend')

  backendProcess = spawn(cmd, args, {
    cwd,
    stdio: ['ignore', 'pipe', 'pipe'],
    env: { ...process.env, PYTHONUNBUFFERED: '1' },
  })

  backendProcess.stdout?.on('data', (d: Buffer) => {
    console.log('[backend]', d.toString().trim())
  })
  backendProcess.stderr?.on('data', (d: Buffer) => {
    console.error('[backend-err]', d.toString().trim())
  })
  backendProcess.on('exit', (code) => {
    console.log('[backend] exited with code', code)
    backendProcess = null
  })

  await waitForHealth()
  console.log('[sidecar] backend is healthy')
}

export function stopSidecar(): void {
  if (backendProcess && !backendProcess.killed) {
    backendProcess.kill('SIGTERM')
    backendProcess = null
  }
}

export const BACKEND_BASE_URL = `http://127.0.0.1:${BACKEND_PORT}`
