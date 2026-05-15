#!/usr/bin/env bash
# experiments/scripts_eval/switch-arm.sh
#
# Flip the seer-cli scripts-eval harness between arm A and arm C and
# export the env vars the harness hooks read. Must be SOURCED, not
# executed (the env exports only stick in the calling shell).
#
# Usage:
#   source experiments/scripts_eval/switch-arm.sh <A|C> <run_id>
#
# Arm A: hides .claude/skills/repo-map -> .claude/skills/_repo-map.disabled
#        and sets SEER_EVAL_ARM=A.
# Arm C: restores .claude/skills/_repo-map.disabled -> .claude/skills/repo-map
#        and sets SEER_EVAL_ARM=C.
# Both arms: export SEER_EVAL_RUN_ID=<run_id>.
#
# Idempotent: re-sourcing with the same (arm, run_id) is a no-op on
# disk and re-exports the env vars unchanged. Switching arms flips the
# disk state symmetrically.
#
# Exit codes (returned to the sourcing shell):
#   0  success
#   2  usage error (missing args or invalid arm)
#   3  refuse: both repo-map and _repo-map.disabled exist

# Refuse direct execution -- the caller would lose the env vars.
if [ "${BASH_SOURCE[0]:-$0}" = "${0}" ]; then
    echo "switch-arm.sh: must be SOURCED, not executed." >&2
    echo "  usage: source experiments/scripts_eval/switch-arm.sh <A|C> <run_id>" >&2
    exit 1
fi

# Wrap the body so locals stay scoped; unset the function after.
_seer_switch_arm() {
    local arm="${1:-}"
    local run_id="${2:-}"

    if [ -z "$arm" ] || [ -z "$run_id" ]; then
        echo "switch-arm.sh: usage: source switch-arm.sh <A|C> <run_id>" >&2
        return 2
    fi

    local script_path="${BASH_SOURCE[0]}"
    local script_dir
    script_dir="$(cd "$(dirname "$script_path")" && pwd)"
    local repo_root
    repo_root="$(cd "$script_dir/../.." && pwd)"
    local enabled="$repo_root/.claude/skills/repo-map"
    local disabled="$repo_root/.claude/skills/_repo-map.disabled"

    if [ -d "$enabled" ] && [ -d "$disabled" ]; then
        echo "switch-arm.sh: BOTH '$enabled' and" >&2
        echo "  '$disabled' exist; refusing to clobber." >&2
        echo "  Resolve manually, then re-source." >&2
        return 3
    fi

    case "${arm^^}" in
        A)
            if [ -d "$enabled" ]; then
                mv "$enabled" "$disabled"
                echo "arm A: moved repo-map -> _repo-map.disabled" >&2
            else
                echo "arm A: repo-map already disabled (no-op on disk)" >&2
            fi
            export SEER_EVAL_RUN_ID="$run_id"
            export SEER_EVAL_ARM="A"
            ;;
        C)
            if [ -d "$disabled" ]; then
                mv "$disabled" "$enabled"
                echo "arm C: restored _repo-map.disabled -> repo-map" >&2
            else
                echo "arm C: repo-map already enabled (no-op on disk)" >&2
            fi
            export SEER_EVAL_RUN_ID="$run_id"
            export SEER_EVAL_ARM="C"
            ;;
        *)
            echo "switch-arm.sh: arm must be A or C, got: '$arm'" >&2
            return 2
            ;;
    esac

    echo "exported SEER_EVAL_RUN_ID=$SEER_EVAL_RUN_ID SEER_EVAL_ARM=$SEER_EVAL_ARM" >&2
}

_seer_switch_arm "$@"
_seer_switch_arm_rc=$?
unset -f _seer_switch_arm
return $_seer_switch_arm_rc
