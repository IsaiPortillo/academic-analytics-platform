#!/bin/bash
# =============================================================================
# Despliega Sistema Minerva (rama develop) en el servidor. Ejecutar como root:
#
#   desplegar-minerva
#
# Instalación (una vez):
#   cp /var/www/academic-analytics-platform/deploy/desplegar-minerva.sh /usr/local/bin/desplegar-minerva
#   chmod +x /usr/local/bin/desplegar-minerva
#
# Qué hace: trae el código, instala dependencias, instala/actualiza las unidades de
# systemd (web y dashboard de Streamlit), devuelve el repo a `ubuntu` y reinicia ambos
# servicios. Lo que NO hace, a propósito, porque es de una sola vez o es tuyo:
#   - el vhost de nginx (deploy/nginx-edumetrics.conf es la referencia)
#   - las migraciones de base de datos (database/oltp/NN_*.sql) ni `python -m etl.carga`
#   - el .env
# =============================================================================
set -euo pipefail

# Todo dentro de una función y `exit` al final: el script puede actualizarse a sí
# mismo con el git pull y bash lee los scripts por partes; así no se confunde.
main() {
    R=/var/www/academic-analytics-platform
    U=ubuntu
    [ "$(id -u)" -eq 0 ] || { echo "Ejecútalo como root: sudo desplegar-minerva"; exit 1; }

    echo "== 1/6 Código (develop)"
    sudo -u "$U" git -C "$R" pull --ff-only origin develop

    echo "== 2/6 Dependencias"
    sudo -u "$U" bash -lc "cd $R && export PATH=\$HOME/.local/bin:\$PATH && uv pip install --python .venv/bin/python -q -r backend/requirements.txt -r etl/requirements.txt -r dashboard/requirements.txt"

    echo "== 3/6 Servicios de systemd"
    for unidad in academico-web academico-streamlit; do
        install -m 644 "$R/deploy/$unidad.service" "/etc/systemd/system/$unidad.service"
    done
    systemctl daemon-reload
    systemctl enable academico-web academico-streamlit >/dev/null 2>&1

    echo "== 4/6 Permisos (devuelve el repo a $U)"
    chown -R "$U:$U" "$R"

    echo "== 5/6 Reinicio"
    systemctl restart academico-web academico-streamlit
    sleep 5

    echo "== 6/6 Comprobaciones"
    systemctl is-active academico-web academico-streamlit
    curl -s -o /dev/null -w "web      127.0.0.1:8000/login            -> %{http_code}\n" http://127.0.0.1:8000/login
    curl -s -o /dev/null -w "streamlit 127.0.0.1:8501/analitica/_stcore/health -> %{http_code}\n" http://127.0.0.1:8501/analitica/_stcore/health

    # Avisos de lo que queda por hacer a mano
    grep -q '^DASHBOARD_STREAMLIT_URL=' "$R/.env" 2>/dev/null \
        || echo "AVISO: falta DASHBOARD_STREAMLIT_URL=/analitica/ en $R/.env (el menú no mostrará el dashboard)."
    grep -rqs 'auth_request' /etc/nginx/sites-enabled/ \
        || echo "AVISO: nginx todavía no tiene el bloque /analitica/ con auth_request (ver deploy/nginx-edumetrics.conf): el dashboard no es accesible por enlace."
}

main "$@"
exit 0
