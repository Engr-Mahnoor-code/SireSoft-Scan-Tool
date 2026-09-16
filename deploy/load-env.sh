#!/bin/bash
# Loads the project .env into the environment. Sourced by the run-*.sh wrappers,
# never executed on its own.
#
# `. .env` does not work here. That runs the file as shell code, but the values
# are data: a Django SECRET_KEY is full of characters bash treats as syntax —
# parentheses, #, !, & — and a password may well be too. Sourcing one of those
# fails with "syntax error near unexpected token" before the service ever starts.
# So read each line and export it verbatim instead.

_env_file="${PROJECT_DIR:?PROJECT_DIR must be set before sourcing load-env.sh}/.env"

if [ ! -f "$_env_file" ]; then
    echo "[ERROR] No .env found at $_env_file" >&2
    echo "        Copy .env.example to .env and fill it in." >&2
    exit 1
fi

while IFS= read -r _line || [ -n "$_line" ]; do
    case "$_line" in
        '' | '#'*) continue ;;   # blank line or comment
        *=*) ;;                  # a KEY=VALUE line
        *) continue ;;           # anything else is not a setting
    esac

    _key=${_line%%=*}
    _value=${_line#*=}

    # Tolerate `export KEY=value` and spaces around the name.
    _key=${_key#export }
    _key=${_key// /}
    [ -n "$_key" ] || continue

    # Strip one layer of surrounding quotes, for .env files that use them.
    case "$_value" in
        \"*\") _value=${_value#\"}; _value=${_value%\"} ;;
        \'*\') _value=${_value#\'}; _value=${_value%\'} ;;
    esac

    export "$_key=$_value"
done < "$_env_file"

unset _env_file _line _key _value
