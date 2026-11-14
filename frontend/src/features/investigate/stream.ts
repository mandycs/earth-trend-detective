import { API_URL } from '../explore/api'
import type { InvEvent } from './types'

export type InvestigateBody = { question: string; site_id: string } | { question: string; lat: number; lon: number }

/**
 * POST /investigate and read its Server-Sent Events. EventSource cannot POST,
 * so the stream is read by hand: blocks split on a blank line, `event:` and
 * `data:` lines inside each.
 */
export async function investigate(
  body: InvestigateBody,
  onEvent: (event: InvEvent) => void,
  signal: AbortSignal,
): Promise<void> {
  let response: Response
  try {
    response = await fetch(`${API_URL}/investigate`, {
      method: 'POST',
      headers: { 'content-type': 'application/json', accept: 'text/event-stream' },
      body: JSON.stringify(body),
      signal,
    })
  } catch (cause) {
    if (signal.aborted) throw cause
    throw new Error("We couldn't reach the analysis service. Check your connection and try again.")
  }
  if (!response.ok || !response.body) {
    throw new Error(
      response.status >= 500
        ? 'The investigation failed on the server. Try again in a moment.'
        : 'This question or place could not be investigated. Pick another point and try again.',
    )
  }
  const reader = response.body.pipeThrough(new TextDecoderStream()).getReader()
  let buffer = ''
  for (;;) {
    const { value, done } = await reader.read()
    if (done) break
    buffer += value.replace(/\r\n/g, '\n')
    let cut = buffer.indexOf('\n\n')
    while (cut !== -1) {
      const block = buffer.slice(0, cut)
      buffer = buffer.slice(cut + 2)
      let name = 'message'
      const data: string[] = []
      for (const line of block.split('\n')) {
        if (line.startsWith('event:')) name = line.slice(6).trim()
        else if (line.startsWith('data:')) data.push(line.slice(5).trimStart())
      }
      if (data.length > 0 || name !== 'message') {
        let parsed: unknown = null
        try {
          parsed = data.length ? JSON.parse(data.join('\n')) : null
        } catch {
          parsed = data.join('\n')
        }
        onEvent({ event: name, data: parsed } as InvEvent)
      }
      cut = buffer.indexOf('\n\n')
    }
  }
}
