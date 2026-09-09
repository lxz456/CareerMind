import request from './index'

export const startInterview = (data) => request.post('/interview/start', data)
export async function streamAnswer(sessionId, answer, onEvent) {
  const token = localStorage.getItem('careermind_token')
  const response = await fetch(`${request.defaults.baseURL}/interview/${sessionId}/answer`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
    body: JSON.stringify({ answer }),
  })
  if (!response.ok) {
    const body = await response.json().catch(() => ({}))
    throw new Error(body.detail || `请求失败 (${response.status})`)
  }
  if (!response.body) throw new Error('浏览器不支持流式响应')

  const reader = response.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''
  let session = null

  const consumeBlock = (block) => {
    const data = block.split('\n')
      .filter(line => line.startsWith('data:'))
      .map(line => line.slice(5).trimStart())
      .join('\n')
    if (!data) return
    const event = JSON.parse(data)
    onEvent?.(event)
    if (event.type === 'error') throw new Error(event.message || '面试处理失败')
    if (event.session) session = event.session
  }

  while (true) {
    const { value, done } = await reader.read()
    buffer += decoder.decode(value || new Uint8Array(), { stream: !done }).replace(/\r\n/g, '\n')
    let boundary
    while ((boundary = buffer.indexOf('\n\n')) >= 0) {
      consumeBlock(buffer.slice(0, boundary))
      buffer = buffer.slice(boundary + 2)
    }
    if (done) break
  }
  if (buffer.trim()) consumeBlock(buffer)
  if (!session) throw new Error('流式响应未返回最终会话状态')
  return session
}
export const getFeedback = (sessionId) =>
  request.get(`/interview/${sessionId}/feedback`)
export const listSessions = () => request.get('/interview/sessions')
export const deleteSession = (sessionId) => request.delete(`/interview/${sessionId}`)
