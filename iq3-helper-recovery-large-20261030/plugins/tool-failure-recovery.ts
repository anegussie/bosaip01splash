import { record } from "./lib/telemetry.ts"
import { lstat } from "node:fs/promises"
import { randomUUID } from "node:crypto"
import { isAbsolute } from "node:path"

type Failure = { key: string; tool: string; kind: "schema" | "incomplete" | "payload_size" | "external_directory" | "shell_portability" }
const mutationTools = new Set(["write", "edit", "shell", "bash", "execute"])
const recoveryBytes = 3000
const singleLine = "^[^\\x00-\\x1F\\x7F]*$"
const iq3Worker = (event: any) => ["general_worker", "context_worker"].includes(event.agent)
  && event.model?.providerID === "local-llama" && event.model?.id === "qwen3.6-35b-a3b-iq3-xxs-splash"

// Qwen's XML string parameters are raw even for strict tools. The bounded
// response-format envelope invokes the backend's JSON grammar instead.
function boundedInput(tool: string, original: any): any {
  if (original?.type !== "object" || !original.properties || original.additionalProperties !== false)
    throw new Error(`Unsupported ${tool} argument schema`)
  const schema = structuredClone(original)
  const caps: Record<string, number> = tool === "edit"
    ? { path: 160, oldString: 256, newString: 384 }
    : tool === "write" ? { path: 160, content: 240 }
    : tool === "execute" ? { code: 1024 } : { command: 1024, workdir: 160 }
  for (const [name, value] of Object.entries(schema.properties) as [string, any][]) {
    if (value.type === "string") {
      if (!caps[name] || value.minLength > caps[name]) throw new Error(`Unsupported ${tool}.${name} string bound`)
      value.maxLength = Math.min(value.maxLength ?? Infinity, caps[name])
    } else if (!["boolean", "integer", "number"].includes(value.type)) {
      throw new Error(`Unsupported ${tool}.${name} argument type`)
    }
  }
  return schema
}

function checkedInput(schema: any, value: any): boolean {
  if (!value || typeof value !== "object" || Array.isArray(value)) return false
  if (Object.keys(value).some(key => !Object.hasOwn(schema.properties, key))) return false
  if ((schema.required ?? []).some((key: string) => !Object.hasOwn(value, key))) return false
  return Object.entries(value).every(([key, item]) => {
    const rule = schema.properties[key]
    if (rule.type !== "string") return true // Original native validation still runs.
    // A value at the decoder boundary may be a forcibly closed source string.
    // Never execute it as though it were a complete user-intended patch/script.
    return typeof item === "string" && Array.from(item).length < rule.maxLength
      && Array.from(item).length >= (rule.minLength ?? 0)
      && !(rule.pattern === singleLine && /[\x00-\x1F\x7F]/.test(item))
  }) && new TextEncoder().encode(JSON.stringify(value)).length <= recoveryBytes
}

function compactIncompleteError(text: string): string {
  try {
    const value = JSON.parse(text), error = value?.error
    if (error?.type !== "tool.input-incomplete" || typeof error.message !== "string"
      || !/^The tool call was not executed because the output token limit\b/.test(error.message)) return text
    const boundary = error.message.indexOf("\n\nInput excerpt ")
    if (boundary < 0) return text
    return JSON.stringify({ ...value, error: { ...error, message: error.message.slice(0, boundary) } })
  } catch { return text }
}

function apiStream(api: any, message: any, finish: string): Response {
  const base = { id: api.id ?? "bounded-tool-generation", object: "chat.completion.chunk", created: api.created ?? 0, model: api.model ?? "local" }
  const frame = (delta: any, reason: string | null, usage?: any) => `data: ${JSON.stringify({ ...base,
    choices: [{ index: 0, delta, finish_reason: reason }], ...(usage ? { usage } : {}),
  })}\n\n`
  const delta: any = { role: "assistant", ...(message.content != null ? { content: message.content } : {}) }
  if (message.tool_calls?.length) delta.tool_calls = message.tool_calls.map((call: any, index: number) => ({ index, ...call }))
  return new Response(frame(delta, null) + frame({}, finish, api.usage) + "data: [DONE]\n\n", { headers: { "content-type": "text/event-stream" } })
}

function failure(part: any): Failure | undefined {
  if (part?.type !== "tool-result" || !["text", "error", "error-text", "error-json"].includes(part.result?.type)) return
  const value = part.result.value
  const message = typeof value === "string" ? value : value?.error?.message ?? value?.message
  const tool = part.name ?? part.tool
  if (typeof message !== "string" || typeof tool !== "string") return
  // Native shell pipelines can report success when a later stage masks BSD
  // grep's exit code. Recover from the actual diagnostic, not inferred syntax.
  if (["shell", "bash"].includes(tool)
    && /(?:^|\n)(?:\/usr\/bin\/)?grep: (?:invalid|illegal) option -- ['"]?P['"]?(?:\r?\n|$)/.test(message)
    && /(?:^|\n)usage: grep \[/.test(message))
    return { tool, kind: "shell_portability", key: "grep:unsupported-P" }
  if (!["error", "error-text", "error-json"].includes(part.result?.type)) return
  // Question failures already have a one-attempt, current-turn fallback.
  if (tool !== "question" && message.startsWith(`Invalid arguments for tool "${tool}":`)) {
    // Exclude payloads: changed JSON with the same diagnostic is still the
    // same failure, and source/prompt contents must not enter telemetry.
    return { tool, kind: "schema", key: `${tool}:${message.split(/\n\s*Arguments provided:/)[0].trim()}` }
  }
  if (/^The tool call was not executed because the output token limit\b/.test(message))
    return { tool, kind: "incomplete", key: `${tool}:incomplete` }
  if (/^TOOL_PAYLOAD_SIZE_STOP:/.test(message))
    return { tool, kind: "payload_size", key: `${tool}:payload_size` }
  if (message === "Permission denied: external_directory")
    return { tool, kind: "external_directory", key: "external_directory" }
}

// Derive recovery from actual tool results after the latest user message.
// This covers parent/child sessions, survives reloads, and adds no call budget.
export default {
  id: "tool-failure-recovery",
  async setup(ctx: any) {
    const repairs = new Map<string, { tool?: string; partial?: string; bounded?: boolean }>()
    const requests = new Map<string, { sessionID: string; wrapped: Map<string, any>; allowed: Set<string>; allowFinal: boolean }>()
    await ctx.tool?.hook("execute.before", async (event: any) => {
      const state = repairs.get(event.sessionID)
      if (!state?.bounded || !mutationTools.has(event.tool)) return
      if (event.tool === "write" && typeof event.input?.path === "string") {
        if (!isAbsolute(event.input.path))
          throw new Error("TOOL_PAYLOAD_SIZE_STOP: bounded write requires an absolute path so existing-file protection checks the same destination as the native tool.")
        try {
          await lstat(event.input.path)
          throw new Error("TOOL_PAYLOAD_SIZE_STOP: bounded write cannot overwrite an existing path. Use an exact-match edit so a decoder-limited string cannot replace the entire file.")
        } catch (error: any) {
          if (error.code !== "ENOENT") throw error
        }
      }
      // Bound generated arguments, never the size of a script's eventual output.
      if (new TextEncoder().encode(JSON.stringify(event.input ?? {})).length > recoveryBytes)
        throw new Error(`TOOL_PAYLOAD_SIZE_STOP: ${event.tool} correction exceeds ${recoveryBytes} UTF-8 bytes of serialized arguments. This call was rejected before execution. Return PARTIAL with the unfinished work; do not replay it or switch tools to bypass the bound.`)
    })
    await ctx.session.hook("context", async (event: any) => {
      repairs.delete(event.sessionID)
      if (event.model?.providerID !== "local-llama") return
      const messages = event.messages ?? []
      const boundary = messages.findLastIndex((message: any) => message.role === "user")
      if (boundary < 0) return
      const current = messages.slice(boundary + 1)
      const pending = new Map<string, { failure: Failure; count: number }>()
      let bounded = false
      for (const message of current) {
        if (message.role !== "tool" || !Array.isArray(message.content)) continue
        for (const part of message.content) {
          if (part.type !== "tool-result") continue
          const item = failure(part)
          if (item) {
            if (item.kind === "incomplete" && mutationTools.has(item.tool)) bounded = true
            pending.set(item.key, { failure: item, count: (pending.get(item.key)?.count ?? 0) + 1 })
          } else if (part.result?.type && !["error", "error-text", "error-json"].includes(part.result.type)) {
            const tool = part.name ?? part.tool
            for (const [key, previous] of pending) {
              if (previous.failure.tool === tool
                || (previous.failure.kind === "incomplete" && bounded && iq3Worker(event) && mutationTools.has(tool) && mutationTools.has(previous.failure.tool))
                || (previous.failure.kind === "external_directory" && ["read", "write", "edit", "shell", "bash"].includes(tool))) pending.delete(key)
            }
          }
        }
      }
      bounded = bounded && iq3Worker(event) && Object.keys(event.tools ?? {}).some(tool => mutationTools.has(tool))
      if (!pending.size && !bounded) return
      if (bounded) repairs.set(event.sessionID, { bounded: true })
      const stopped = [...pending.values()].find(item => item.count >= 2 || item.failure.kind === "payload_size")
      let text: string
      if (stopped) {
        event.tools = {}
        text = `TOOL_FAILURE_STOP: ${stopped.failure.tool} failed twice with the same ${stopped.failure.kind} condition in this user turn. Return STATUS: PARTIAL with the actual failure, confirmed changes/checks, and remaining work. No further tools, retries, replacement workers, or claims of completion. A new user request can authorize recovery.`
        if (iq3Worker(event) && ["incomplete", "payload_size"].includes(stopped.failure.kind)) {
          text = `TOOL_FAILURE_STOP: ${stopped.failure.tool} has exhausted its bounded argument correction. Return PARTIAL with recorded progress and remaining work; do not generate replacement source or commands.`
          const partial = `STATUS: PARTIAL\nTOOL_FAILURE_STOP: ${stopped.failure.tool} could not complete a bounded payload correction (${stopped.failure.kind}). The rejected/incomplete calls did not execute.\nCHANGED/CHECKS: Earlier successful tool results remain recorded in this session; no additional edits or checks were performed by this handoff. Completion of the requested edit and verification is unconfirmed.\nNEXT: Retain those results and resume only on a new user request with a smaller source-reusing edit or data batch. No replacement worker was launched.`
          repairs.set(event.sessionID, { partial })
        }
      } else if (bounded) {
        const incomplete = [...pending.values()].find(item => item.failure.kind === "incomplete" && mutationTools.has(item.failure.tool) && event.tools?.[item.failure.tool])
        const tool = incomplete ? (incomplete.failure.tool === "write" && event.tools?.edit ? "edit" : incomplete.failure.tool) : undefined
        repairs.set(event.sessionID, { tool, bounded: true })
        text = `TOOL_PAYLOAD_RECOVERY: An incomplete mutation never executed. ${tool ? `Use the advertised ${tool} tool now for ONE complete small correction.` : "Continue the remaining work in small complete batches; reads and checks remain available."} Mutating tools now accept an input OBJECT containing their original arguments. The object schema enforces short strings during generation. For the first edit, use ONE existing source line from a successful read, with no control characters. Omit its display line-number prefix; if indentation has tabs, use a unique printable substring without that indentation. Add ONE row's fields while preserving the rest. Failed argument excerpts are invalid generated input, not source evidence: never copy their escaped quotes or newline text. Do not emit whole arrays or replacement files. Writes may create new helper files only; use edit to append or change an existing file. Each string must finish naturally below its schema maximum: a value reaching the boundary is rejected, never silently accepted as truncated source. Prefer a direct edit or one complete short source-reusing shell transformation/check. In shell, set workdir to the selected project and use relative filenames to save payload. The execute tool is confined Code Mode JavaScript: require, imports and direct filesystem access are unavailable; use only its advertised catalog tools, or choose the ordinary shell tool for a local Node/Python transformation. Preserve the original objective, exclusions and required checks, continue remaining rows after each successful edit, then run the focused check. A second incomplete or oversized correction stops with PARTIAL.`
      } else if ([...pending.values()].some(item => item.failure.kind === "shell_portability")) {
        text = "SHELL_PORTABILITY_RECOVERY: The actual shell output reports that this host's grep does not support -P, even if the pipeline exit code was zero. Do not use grep -P again. Preserve the requested task and checks; choose a portable equivalent with matching pattern semantics, installed rg, or Python's standard library. Do not blindly replace PCRE syntax with -E. Keep permitted project-local helpers and read-only shell checks available. Correct the unsupported command once and verify the real result; do not repeat already successful checks."
      } else {
        text = "TOOL_FAILURE_RECOVERY: A tool failed before useful execution. Correct the reported schema fields once, supplying complete arguments; never repeat an empty object. If output was cut off, shorten the delegation to objective, exact project path and checks; do not embed scripts or data tables. Split file payloads into smaller complete calls. For Permission denied: external_directory, keep the restriction: use a scratch/helper path inside the selected project, with a permitted working directory. Do not retry the denied external path or switch commands to bypass permission. If essential external access is required, report the exact permission blocker. A second identical failure ends this turn with a factual PARTIAL handoff."
      }
      if (repairs.size > 128) repairs.delete(repairs.keys().next().value!)
      const present = current.some((message: any) => message.role === "system" && Array.isArray(message.content) && message.content.some((part: any) => part.type === "text" && part.text === text))
      if (!present) {
        messages.push({ role: "system", content: [{ type: "text", text }] })
        await record({ event: "tool_failure_recovery", sessionID: event.sessionID, action: stopped ? "partial_handoff" : "one_correction", kinds: [...new Set([...pending.values()].map(item => item.failure.kind))] })
      }
    })
    await ctx.session.hook("http.request", async (event: any) => {
      const state = repairs.get(event.sessionID)
      if (!state?.bounded || event.kind !== "primary" || event.model?.providerID !== "local-llama"
        || !new URL(event.request.url).pathname.endsWith("/chat/completions")) return
      const body = await event.request.clone().json()
      // Project only failed-input diagnostics on the wire. Successful source
      // evidence and the native stored transcript retain their exact contents.
      for (const message of body.messages ?? []) {
        if (message.role !== "tool") continue
        if (typeof message.content === "string") message.content = compactIncompleteError(message.content)
        else if (Array.isArray(message.content)) for (const part of message.content) {
          if (part.type === "text" && typeof part.text === "string") part.text = compactIncompleteError(part.text)
        }
      }
      if (state.tool && !body.tools?.some((tool: any) => tool.function?.name === state.tool)) {
        if (body.tools?.some((tool: any) => mutationTools.has(tool.function?.name)))
          throw new Error(`STATUS: PARTIAL\nTOOL_FAILURE_STOP: The selected ${state.tool} correction is not advertised on this request; no unbounded mutation was sent.`)
        return
      }
      const wrapped = new Map<string, any>()
      for (const entry of body.tools ?? []) {
        const fn = entry.function
        if (!mutationTools.has(fn?.name)) continue
        try {
          const schema = boundedInput(fn.name, fn.parameters)
          if (state.tool === "edit" && fn.name === "edit") for (const name of ["oldString", "newString"]) {
            const rule = schema.properties[name]
            if (rule?.type === "string" && rule.pattern == null) rule.pattern = singleLine
          }
          wrapped.set(fn.name, schema)
          fn.parameters = schema
        } catch {
          // Never quietly replay an unsupported mutation schema unbounded.
          body.tools = body.tools.filter((tool: any) => tool !== entry)
        }
      }
      if (state.tool) {
        if (!wrapped.has(state.tool)) throw new Error(`TOOL_FAILURE_STOP: Cannot safely bound the advertised ${state.tool} schema`)
        body.tools = body.tools.filter((tool: any) => tool.function?.name === state.tool)
        body.tool_choice = { type: "function", function: { name: state.tool } }
      }
      if (!body.tools?.length) throw new Error("STATUS: PARTIAL\nTOOL_FAILURE_STOP: No supported bounded mutation schema or remaining read/check tool is available.")
      const allowed = new Set<string>((body.tools ?? []).map((tool: any) => tool.function?.name))
      for (const name of wrapped.keys()) if (!allowed.has(name)) wrapped.delete(name)
      const allowFinal = !state.tool
      const branches: any[] = body.tools.map((tool: any) => ({ type: "object",
        description: (tool.function.description ?? "").slice(0, 500),
        properties: { tool: { type: "string", const: tool.function.name }, input: tool.function.parameters },
        required: ["tool", "input"], additionalProperties: false,
      }))
      if (allowFinal) branches.push({ type: "object", properties: { text: { type: "string", maxLength: 1024 } }, required: ["text"], additionalProperties: false })
      const descriptions = body.tools.map((tool: any) => `${tool.function.name}: ${(tool.function.description ?? "").slice(0, 500)}`).join("\n")
      body.messages.push({ role: "system", content: `BOUNDED_OPERATION_JSON: Return only JSON data matching the response schema. This request has no XML/function-call protocol. For one operation return {"tool":"operation_name","input":{the original arguments}}. ${allowFinal ? 'After all requested edits and checks finish, return {"text":"your concise factual final"}.' : `The current correction must use ${state.tool}; no final or other operation is available yet.`} Code and source strings must be complete; do not put XML markers or protocol-closing text inside them. Preserve the task, source evidence and required checks. Available original operations:\n${descriptions}` })
      body.response_format = { type: "json_schema", json_schema: { name: "bounded_operation", strict: true, schema: { oneOf: branches } } }
      delete body.tools
      delete body.tool_choice
      delete body.parallel_tool_calls
      body.stream = false
      delete body.stream_options
      const headers = new Headers(event.request.headers); headers.delete("content-length")
      const nonce = randomUUID()
      headers.set("x-opencode-bounded-tool-request", nonce)
      event.request = new Request(event.request, { headers, body: JSON.stringify(body) })
      requests.set(nonce, { sessionID: event.sessionID, wrapped, allowed, allowFinal })
      event.request.signal.addEventListener("abort", () => requests.delete(nonce), { once: true })
      if (requests.size > 128) requests.delete(requests.keys().next().value!)
    })
    await ctx.session.hook("http.response", async (event: any) => {
      const nonce = event.request.headers.get("x-opencode-bounded-tool-request")
      const request = nonce && requests.get(nonce)
      if (request && request.sessionID === event.sessionID) {
        requests.delete(nonce)
        if (!event.response.ok || event.request.signal.aborted) return
        let api: any
        try {
          api = await event.response.json()
          if (event.request.signal.aborted) return
          const choice = api.choices?.[0], message = choice?.message
          if (api.choices?.length !== 1 || !message || choice.finish_reason !== "stop"
            || typeof message.content !== "string" || message.tool_calls?.length)
            throw new Error("bounded generation did not finish completely")
          const operation = JSON.parse(message.content)
          if (!operation || typeof operation !== "object" || Array.isArray(operation)) throw new Error("malformed bounded operation")
          if (request.allowFinal && Object.keys(operation).length === 1 && typeof operation.text === "string" && Array.from(operation.text).length < 1024) {
            event.response = apiStream(api, { content: operation.text }, "stop")
          } else {
            if (Object.keys(operation).length !== 2 || !Object.hasOwn(operation, "input") || !request.allowed.has(operation.tool)
              || !operation.input || typeof operation.input !== "object" || Array.isArray(operation.input)) throw new Error("unadvertised or malformed bounded tool")
            const schema = request.wrapped.get(operation.tool)
            if (schema && !checkedInput(schema, operation.input)) throw new Error("bounded arguments were oversized or reached their string limit")
            event.response = apiStream(api, { tool_calls: [{ id: `bounded-${nonce}`, type: "function", function: {
              name: operation.tool, arguments: JSON.stringify(operation.input),
            } }] }, "tool_calls")
          }
          await record({ event: "bounded_tool_generation", sessionID: event.sessionID, action: "unwrap_complete_arguments", tools: [...request.wrapped.keys()] })
        } catch (error) {
          if (event.request.signal.aborted) throw error
          event.response = apiStream(api ?? {}, { content: "STATUS: PARTIAL\nTOOL_FAILURE_STOP: Bounded mutation generation did not produce complete arguments below the schema limits. No generated mutation from this response was executed. Earlier progress remains recorded; the requested work and verification remain unfinished." }, "stop")
          await record({ event: "bounded_tool_generation", sessionID: event.sessionID, action: "reject_incomplete_or_boundary_arguments" })
        }
        return
      }
      const partial = repairs.get(event.sessionID)?.partial
      if (!partial || event.kind !== "primary" || event.model?.providerID !== "local-llama"
        || !new URL(event.request.url).pathname.endsWith("/chat/completions")
        || !event.response.ok || !event.response.body
        || !event.response.headers.get("content-type")?.includes("text/event-stream")) return
      void event.response.body.cancel("TOOL_FAILURE_STOP: recorded incomplete arguments").catch(() => {})
      const frame = (delta: any, finish_reason: string | null) => `data: ${JSON.stringify({
        id: "bounded-tool-payload-handoff", object: "chat.completion.chunk", created: 0,
        model: event.model.id ?? "local", choices: [{ index: 0, delta, finish_reason }],
      })}\n\n`
      event.response = new Response(frame({ role: "assistant", content: partial }, null) + frame({}, "stop") + "data: [DONE]\n\n", {
        headers: { "content-type": "text/event-stream" },
      })
      await record({ event: "tool_payload_handoff", sessionID: event.sessionID, action: "cancel_generation_and_return_recorded_result" })
    })
  },
}
