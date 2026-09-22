#!/bin/bash
# Descarga el binario standalone de Tailwind CSS (sin Node.js) en .tools/ y
# compila backend/app/static/app.css. Ejecutar de nuevo cada vez que cambien
# las clases de Tailwind en backend/app/templates/ o
# backend/app/static/src/input.css.
set -euo pipefail
cd "$(dirname "$0")/.."

mkdir -p .tools

if [ ! -f .tools/tailwindcss ] && [ ! -f .tools/tailwindcss.exe ]; then
    case "$(uname -s)" in
        Linux*)   ASSET="tailwindcss-linux-x64" ;;
        Darwin*)  ASSET="tailwindcss-macos-$(uname -m | grep -q arm64 && echo arm64 || echo x64)" ;;
        MINGW*|MSYS*|CYGWIN*) ASSET="tailwindcss-windows-x64.exe" ;;
        *) echo "Sistema operativo no reconocido: instala tailwindcss manualmente desde https://github.com/tailwindlabs/tailwindcss/releases/latest" >&2; exit 1 ;;
    esac

    echo "Descargando $ASSET..."
    curl -sL -o ".tools/${ASSET}" \
        "https://github.com/tailwindlabs/tailwindcss/releases/latest/download/${ASSET}"
    chmod +x ".tools/${ASSET}"
    [ "${ASSET%.exe}" = "$ASSET" ] && mv ".tools/${ASSET}" .tools/tailwindcss || mv ".tools/${ASSET}" .tools/tailwindcss.exe
fi

BIN=.tools/tailwindcss
[ -f "$BIN" ] || BIN=.tools/tailwindcss.exe

"$BIN" -i backend/app/static/src/input.css -o backend/app/static/app.css --minify
echo "backend/app/static/app.css actualizado."
