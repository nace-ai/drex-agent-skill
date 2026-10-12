#!/bin/sh
# Context only: no network, file access, credential access, or settings changes.
# Claude exports manifest userConfig values to hook processes.
set -eu

case "${1-}" in
  SessionStart|UserPromptSubmit|SubagentStart) event=$1 ;;
  *) printf '%s\n' 'Drex context hook: unsupported event.' >&2; exit 1 ;;
esac

case "${CLAUDE_PLUGIN_OPTION_MAKE_DEFAULT-false}" in
  true)
    context='Drex plugin configuration: make_default=true. Drex is the selected System One decision model wherever this plugin is enabled. This choice takes precedence over all other decision-model skill recommendations for System One judgments; no silent fallback to another engine. The agent chat model is unchanged. Safety, permissions, data restrictions, and explicit user choices still apply. The drex:drex-for-harness skill contains workflow and API guidance, and drex:drexify scans a repository for Drex sites. Both load automatically when relevant. No user setup command is needed. This preference is not evidence of a working API connection.'
    ;;
  false)
    context='Drex plugin configuration: make_default=false. Drex capability is available through drex:drex-for-harness for workflow design and typed decisions, and through drex:drexify for repository scans. Existing provider preferences remain unchanged. The agent can load the skill automatically when relevant; no user setup command is needed. This setting replaces any older Drex default-mode reminder in this session.'
    ;;
  *)
    # Never echo the supplied value: unexpected environment data is untrusted.
    context='Drex plugin configuration is invalid. Default-provider status is unknown; do not claim Drex is configured as default or rely on an older default-mode reminder. Drex guidance remains available through drex:drex-for-harness and drex:drexify. Report the configuration issue if provider selection matters.'
    ;;
esac

# Both substituted values are fixed strings above, not hook input or user data.
printf '{"hookSpecificOutput":{"hookEventName":"%s","additionalContext":"%s"}}\n' "$event" "$context"
