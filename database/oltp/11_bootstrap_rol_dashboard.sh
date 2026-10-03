#!/bin/bash
# =============================================================================
# FASE 4 - HABILITACIÓN DEL ROL DE SOLO LECTURA PARA EL DASHBOARD
# =============================================================================
# El script 10 creó rol_dashboard con SELECT sobre dw_academico y nada más.
# Aquí se le habilita el inicio de sesión, igual que 07 hace con rol_etl.
#
# Va en un .sh y no en un .sql porque la contraseña llega por variable de
# entorno, y los archivos .sql no interpolan el entorno.
#
# En una base ya inicializada, ejecutarlo con:
#   docker exec -i -e DASHBOARD_DB_USER -e DASHBOARD_DB_PASSWORD \
#       academico_postgres bash -s < database/oltp/11_bootstrap_rol_dashboard.sh
# =============================================================================
set -euo pipefail

if [ -z "${DASHBOARD_DB_PASSWORD:-}" ]; then
    echo "ERROR: DASHBOARD_DB_PASSWORD no está definida. Revisa tu archivo .env" >&2
    exit 1
fi

DASHBOARD_USER="${DASHBOARD_DB_USER:-rol_dashboard}"

psql -v ON_ERROR_STOP=1 \
     --username "${POSTGRES_USER:-postgres}" \
     --dbname "${POSTGRES_DB:-academico_db}" \
     -v dash_user="$DASHBOARD_USER" \
     -v dash_pass="$DASHBOARD_DB_PASSWORD" \
     -v db_name="${POSTGRES_DB:-academico_db}" <<'EOSQL'

SELECT format('ALTER ROLE %I LOGIN PASSWORD %L', :'dash_user', :'dash_pass')
\gexec

GRANT CONNECT ON DATABASE :"db_name" TO :"dash_user";

-- ---------------------------------------------------------------------------
-- Deliberadamente NO hay ningún GRANT sobre academico_oltp ni auditoria.
-- Un dashboard sobre las tablas transaccionales es motivo de rechazo del
-- proyecto; este rol no puede hacerlo aunque el código lo intentara.
-- ---------------------------------------------------------------------------

EOSQL

echo "Rol de solo lectura del DW '$DASHBOARD_USER' habilitado para conexión."
