import { execFile } from "node:child_process"
import { promisify } from "node:util"
import { homedir } from "node:os"
import { basename, join, resolve } from "node:path"
import { revision, type Slice } from "./progress-ledger.ts"
import { record } from "./telemetry.ts"

const execute = promisify(execFile)
export const instruction = (text: string) => {
  try { const value = JSON.parse(text); return typeof value === "string" ? value : text } catch { return text }
}
const textOf = (value: any): string => typeof value === "string" ? value
  : Array.isArray(value) ? value.filter(x => x.type === "text").map(x => x.text ?? "").join("\n") : ""
export function implementationOffer(text: string): string | undefined {
  if ((text.match(/^\s*(?:```|~~~)/gm)?.length ?? 0) % 2) return
  if (/\b(?:quoted?|paste[ds]?|example|transcript|excerpt|file (?:says|contains)|source (?:text|content)|PARTIAL|BLOCKED|(?:CHILD|PARENT)_LOOP_[A-Z_]+|cancelled|canceled|interrupted|resource_timeout)\b/i.test(text)) return
  const line = text.trim().split(/\r?\n/).at(-1)!.trim()
  if (/^(?:Would you like me to|Shall I|Should I|May I)\s+(?:implement|apply|fix|refactor)\b[^?\n]*\?$/i.test(line)
    && !/\b(?:or|review|analy[sz]e|recommend|inventory|cancel|stop)\b/i.test(line)) return line
}
const requestUser = (request: string) => { try { return JSON.parse(request)[1] } catch { return undefined } }
export async function approvedPaths(history: Slice[], request: string): Promise<string[]> {
  const rows = await Promise.all(history.filter(row => row.request === request && row.completed && row.evidence && !row.truncated)
    .map(async row => await revision(row.path) === row.revision ? row.path : undefined))
  return [...new Set(rows.filter((path): path is string => Boolean(path)))]
}
export type Approval = { request: string; paths: string[]; userID: string; offer: string; origin: "parent-offer" | "question" }

// Approval comes from canonical native parent messages, never source excerpts
// or context-pasted offers. Only the adjacent offer in the same task qualifies.
export async function nativeYesApproval(sessionID: string, userID: string, history: Slice[]): Promise<Approval | undefined> {
  if (!/^ses_[A-Za-z0-9]+$/.test(sessionID) || !/^msg_[A-Za-z0-9]+$/.test(userID)) return
  try {
    const path = process.env.OPENCODE_DB ?? join(process.env.XDG_DATA_HOME ?? join(homedir(), ".local/share"), "opencode/opencode.db")
    const { stdout } = await execute("sqlite3", ["-readonly", "-json", path,
      `WITH current_user_row AS (SELECT seq FROM session_message WHERE session_id='${sessionID}' AND id='${userID}' AND type='user'),
       selected AS (SELECT seq FROM current_user_row
         UNION ALL SELECT max(seq) FROM session_message WHERE session_id='${sessionID}' AND type='assistant' AND seq<(SELECT seq FROM current_user_row)
         UNION ALL SELECT max(seq) FROM session_message WHERE session_id='${sessionID}' AND type='user' AND seq<(SELECT seq FROM current_user_row))
       SELECT id,type,data,(SELECT count(*) FROM session_message controls WHERE controls.session_id='${sessionID}'
         AND controls.seq>(SELECT max(seq) FROM session_message WHERE session_id='${sessionID}' AND type='assistant' AND seq<(SELECT seq FROM current_user_row))
         AND controls.seq<(SELECT seq FROM current_user_row)
         AND (controls.type='error' OR (controls.type='idle' AND coalesce(json_extract(controls.data,'$.outcome'),'unknown')!='succeeded'))) AS blocked
       FROM session_message WHERE session_id='${sessionID}' AND seq IN (SELECT seq FROM selected) ORDER BY seq DESC`,
    ], { timeout: 3000, maxBuffer: 1024 * 1024 })
    const rows = JSON.parse(stdout || "[]")
    if (rows.length !== 3 || rows[0].blocked || rows[0].id !== userID || rows[0].type !== "user" || rows[1].type !== "assistant" || rows[2].type !== "user") return
    const user = JSON.parse(rows[0].data), assistant = JSON.parse(rows[1].data)
    if (!/^yes(?: please)?[.!\s]*$/i.test(instruction(user.text ?? textOf(user.content)).trim())
      || assistant.content?.some((part: any) => part.type === "tool" || part.type === "tool-call")) return
    const offer = implementationOffer(textOf(assistant.content))
    const request = history.find(row => requestUser(row.request) === rows[2].id)?.request
    if (!offer || !request) return
    let paths = await approvedPaths(history, request)
    const named = offer.match(/\/?[A-Za-z0-9_.\/-]+\.[A-Za-z0-9]{1,12}(?=[?\s,;]|$)/g) ?? []
    if (named.length) {
      const selected = paths.filter(path => named.some(name => name.startsWith("/") ? resolve(name) === path : basename(path) === name))
      if (!named.every(name => selected.some(path => name.startsWith("/") ? resolve(name) === path : basename(path) === name))) return
      paths = selected
    }
    return paths.length ? { request, paths, userID, offer, origin: "parent-offer" } : undefined
  } catch (error) {
    await record({ event: "scoped_approval_lookup_failed", sessionID, error: String(error).slice(0, 180) })
  }
}

export function implementationQuestion(input: any): { offer: string; options: Map<string, string> } | undefined {
  const questions = input?.questions
  if (!Array.isArray(questions) || questions.length !== 1) return
  const q = questions[0]
  if (typeof q.question !== "string" || !/^(?:Which|What)\b[^?\n]*\b(?:implement|apply|fix|refactor)\b[^?\n]*\?$/i.test(q.question.trim())
    || /\b(?:or|review|analy[sz]e|inventory|cancel|stop)\b/i.test(q.question) || !Array.isArray(q.options)) return
  const options = new Map<string, string>()
  for (const option of q.options) {
    if (typeof option.label !== "string" || typeof option.description !== "string" || options.has(option.label)) return
    options.set(option.label, `${option.label} ${option.description}`)
  }
  return options.size ? { offer: q.question, options } : undefined
}
export function implementationAnswer(options: Map<string, string>, answers: any): boolean {
  return Array.isArray(answers) && answers.length === 1 && Array.isArray(answers[0]) && answers[0].length > 0
    && answers[0].every((label: any) => typeof label === "string" && options.has(label)
      && !/\b(?:review|analy[sz]e|inspect|cancel|stop|none|no|later|skip|unknown|not implement)\b/i.test(options.get(label)!))
}
