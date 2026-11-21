# Pi tool call truncation on Splash option 21

On November 21, 2026, Pi stopped while editing `periodic-table.html` through
the local `~/startllamacpp.sh` option 21 profile. The profile served
`ISTA-DASLab/Qwen3.8-Flash-Next-GSQ-RCO-GGUF:Q2_0` with the BF16 DFlash2 draft.
The fix updated the home launcher and the installed Pi configuration.

## Why the edit stopped

The first edit reached the tool and failed its exact-text match. The search
text contained `&alpha;` where the file contained literal `α`. Pi read the
file again and attempted a corrected edit. That tool call ran out of output
tokens while Pi was generating its arguments, so Pi skipped execution.

| Splash request | Prompt tokens | Requested output limit | Generated tokens | Finish reason |
| --- | ---: | ---: | ---: | --- |
| 412, corrected edit | 109,948 | 740 | 740 | `length` |
| 413, retry | 110,098 | 1 | 1 | `length` |

Splash had a 131,072-token context. The home launcher had given Pi the
114,688-token OpenCode input limit as its total context window. Pi's
compaction threshold was 98,304 tokens, and its retention setting also asked
it to keep 98,304 recent tokens. When the session crossed the threshold, Pi
could find no older messages to summarize under that retention setting. Its
request builder then reduced the available output using its own context
estimate and safety margin. The 32,768-token model output setting was a
ceiling. The request-specific limits in the table controlled both attempts.

## Launcher and Pi changes

For option 21, `sync_pi_splash` now writes the full planned Splash context
to the matching model's `contextWindow` in `~/.pi/agent/models.json`. If
Splash rejects the default context and the launcher retries with a smaller
ceiling, the launcher synchronizes Pi with that ceiling before retrying.
OpenCode still receives its own input limit.

The launcher writes a per-model compaction override in
`~/.pi/agent/settings.json`. It normally reserves the larger of 16,384 tokens
or the configured output limit plus Pi's 4,096-token safety margin. If the
reserve would consume the entire window, it uses half the window. The recent
history setting comes from Pi's global `compaction.keepRecentTokens`
(20,000 by default), capped at half the context remaining after the reserve.
This lets Pi select older messages to summarize when compaction is due.

| Pi setting | During the incident | After the local update |
| --- | ---: | ---: |
| `contextWindow` | 114,688 | 131,072 |
| `maxTokens` | 32,768 | 32,768 |
| `reserveTokens` | 16,384 | 36,864 |
| `keepRecentTokens` | 98,304 | 20,000 |

The local update preserved Pi's existing 32,768-token output setting. On a
future option 21 launch, the launcher synchronizes Pi to the selected output
limit, which defaults to 16,384 unless overridden.

## Verification and session recovery

- The Splash telemetry recorded the two `length` outcomes and their requested
  limits. Replaying the saved session with the installed Pi code reproduced
  the 740-token and one-token caps and the lack of a compaction cut point.
  With the repaired settings, Pi selected history to summarize. A simulated
  summary restored the full 32,768-token request allowance in the replay.
- The launcher passed Bash syntax validation and isolated launch checks for
  the default profile, a retry at a 114,681-token ceiling, explicit output
  and OpenCode context overrides, and an 8,192-token context. The existing
  Splash instance remained ready with a 131,072-token context after installation.

To recover the affected session, reopen Pi so it loads the updated
configuration, resume the session, run `/compact`, and retry the edit with
literal `α` in the search text.

## Shared Splash launcher profiles

The same Pi calculation now runs for every profile handled by the shared
Splash launcher path. OpenCode records the server context, input allowance,
and output allowance in separate fields. Its compaction buffer accounts for
tool results and estimation error. The input allowance already reserves the
configured output window.

On option 19's 80K home profile, Pi gets an 81,920-token context, a
16,384-token output limit, a 20,480-token compaction reserve, and a
20,000-token recent-history budget. OpenCode gets an 81,920-token context,
a 65,536-token input allowance, a 16,384-token output limit, and a
4,096-token compaction buffer.

The OpenCode request hook uses option 19's configured output limit for both
parent and worker requests. It honors smaller limits set for individual
requests. Title generation stays capped at 64 tokens, and the
`bounded-compaction` variant stays capped at 2,048 with thinking disabled.
