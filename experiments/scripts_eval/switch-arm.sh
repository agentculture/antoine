#!/usr/bin/env bash
# experiments/scripts_eval/switch-arm.sh
#
# Export the env vars the antoine scripts-eval harness hooks read.
# Must be SOURCED, not executed (the env exports only stick in the
# calling shell).
#
# Usage:
#   source experiments/scripts_eval/switch-arm.sh <A|B|C> <run_id>
#
# Arm semantics (as of the post-move-aside eval skill):
#   A  banned   — rider forbids repo-map + code-lookup
#   B  directed — rider instructs use of repo-map + code-lookup
#   C  organic  — rider permits but does not direct skill use
# This script no longer touches `.claude/skills/repo-map/` on disk;
# the eval skill relies on the verbal rider as the sole guard for arm A.
#
# Idempotent: re-sourcing re-exports the env vars unchanged.
#
# Exit codes (returned to the sourcing shell):
#   0  success
#   2  usage error (missing args or invalid arm)

# Refuse direct execution -- the caller would lose the env vars.
if [ "${BASH_SOURCE[0]:-$0}" = "${0}" ]; then
    echo "switch-arm.sh: must be SOURCED, not executed." >&2
    echo "  usage: source experiments/scripts_eval/switch-arm.sh <A|B|C> <run_id>" >&2
    exit 1
fi

# Wrap the body so locals stay scoped; unset the function after.
_antoine_switch_arm() {
    local arm="${1:-}"
    local run_id="${2:-}"

    if [ -z "$arm" ] || [ -z "$run_id" ]; then
        echo "switch-arm.sh: usage: source switch-arm.sh <A|B|C> <run_id>" >&2
        return 2
    fi

    case "${arm^^}" in
        A|B|C)
            export ANTOINE_EVAL_RUN_ID="$run_id"
            export ANTOINE_EVAL_ARM="${arm^^}"
            ;;
        *)
            echo "switch-arm.sh: arm must be A, B, or C, got: '$arm'" >&2
            return 2
            ;;
    esac

    echo "exported ANTOINE_EVAL_RUN_ID=$ANTOINE_EVAL_RUN_ID ANTOINE_EVAL_ARM=$ANTOINE_EVAL_ARM" >&2
}

_antoine_switch_arm "$@"
_antoine_switch_arm_rc=$?
unset -f _antoine_switch_arm
return $_antoine_switch_arm_rc
