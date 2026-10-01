/** 统一请求封装：拼后端地址、带当前操作人工号、抛网络错误、给页脚留可读说明。 */
const API_BASE = import.meta.env.VITE_API_BASE ?? ''
const OPERATOR_STORAGE_KEY = 'forklift.operatorId'

export function request(path: string, init?: RequestInit): Promise<Response> {
  const url = path.startsWith('http') ? path : `${API_BASE}${path}`
  const operatorId = localStorage.getItem(OPERATOR_STORAGE_KEY) || ''
  const headers = new Headers(init?.headers)
  if (!headers.has('Content-Type')) {
    headers.set('Content-Type', 'application/json')
  }
  if (operatorId) {
    headers.set('X-Operator-Id', operatorId)
  }
  return fetch(url, { ...init, headers }).catch((error: unknown) => {
    const detail = error instanceof Error ? error.message : '请求未送达'
    throw new Error(`接口请求失败：${detail}`)
  })
}

/** 读出后端 ActionResult 里的驳回原因；非 2xx 时退回到 HTTP detail。 */
export async function readActionMessage(response: Response, fallback: string): Promise<string> {
  try {
    const payload = (await response.json()) as { message?: string; detail?: string }
    return payload.message || payload.detail || fallback
  } catch {
    return fallback
  }
}

export async function fetchJson<T>(path: string): Promise<T> {
  const response = await request(path)
  if (!response.ok) {
    throw new Error(`接口返回 ${response.status}，数据未更新`)
  }
  return (await response.json()) as T
}
