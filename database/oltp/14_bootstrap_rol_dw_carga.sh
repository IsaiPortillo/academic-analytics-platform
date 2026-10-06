#!/bin/bash
# =============================================================================
# FASE 3 - HABILITACIÓN DEL ROL DE ESCRITURA DEL DATA WAREHOUSE
# =============================================================================
# El script 13 creó rol_dw_carga con INSERT/TRUNCATE sobre dw_academico y nada
# más, y le retiró esa escritura a rol_etl. Aquí se le habilita el inicio de
# sesión, igual que 07 hace con rol_etl y 11 con rol_dashboard.
#
# La separación es deliberada: rol_etl LEE el OLTP, rol_dw_carga ESCRIBE el DW,
# y ninguno puede hacer lo del otro. Una carga que se equivocara de base no
# podría tocar el sistema transaccional.
#
# Va en un .sh y no en un .sql porque la contraseña llega por variable de
# entorno, y los archivos .sql no interpolan el entorno.
#
# En una base ya inicializada, ejecutarlo con:
#   docker exec -i -e DW_CARGA_DB_USER -e DW_CARGA_DB_PASSWORD \
#       academico_postgres bash -s < database/oltp/14_bootstrap_rol_dw_carga.sh
# =============================================================================
set -euo pipefail

if [ -z "${DW_CARGA_DB_PASSWORD:-}" ]; then
    echo "ERROR: DW_CARGA_DB_PASSWORD no está definida. Revisa tu archivo .env" >&2
    exit 1
fi

DW_CARGA_USER="${DW_CARGA_DB_USER:-rol_dw_carga}"

psql -v ON_ERROR_STOP=1 \
     --username "${POSTGRES_USER:-postgres}" \
     --dbname "${POSTGRES_DB:-academico_db}" \
     -v carga_user="$DW_CARGA_USER" \
     -v carga_pass="$DW_CARGA_DB_PASSWORD" \
     -v db_name="${POSTGRES_DB:-academico_db}" <<'EOSQL'

SELECT format('ALTER ROLE %I LOGIN PASSWORD %L', :'carga_user', :'carga_pass')
\gexec

GRANT CONNECT ON DATABASE :"db_name" TO :"carga_user";

-- ---------------------------------------------------------------------------
-- Deliberadamente NO hay ningún GRANT sobre academico_oltp ni auditoria: este
-- rol solo puede escribir en dw_academico. Lo que la carga escribe llega ya
-- procesado desde el pipeline (que lee con rol_etl), no se consulta aquí.
-- ---------------------------------------------------------------------------

EOSQL

echo "Rol de escritura del DW '$DW_CARGA_USER' habilitado para conexión."
