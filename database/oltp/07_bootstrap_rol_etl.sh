#!/bin/bash
# =============================================================================
# FASE 3 - HABILITACIÓN DEL ROL DE SOLO LECTURA PARA EL ETL
# =============================================================================
# El script 01 creó rol_etl como contenedor de permisos (SELECT sobre el
# esquema operacional) pero sin LOGIN ni contraseña: nadie podía conectarse con
# él. Aquí se le habilita el acceso, igual que 06 hace con rol_app.
#
# Va en un .sh y no en un .sql porque la contraseña llega por variable de
# entorno, y los archivos .sql no interpolan el entorno.
# =============================================================================
set -euo pipefail

if [ -z "${ETL_DB_PASSWORD:-}" ]; then
    echo "ERROR: ETL_DB_PASSWORD no está definida. Revisa tu archivo .env" >&2
    exit 1
fi

ETL_USER="${ETL_DB_USER:-rol_etl}"

psql -v ON_ERROR_STOP=1 \
     --username "$POSTGRES_USER" \
     --dbname "$POSTGRES_DB" \
     -v etl_user="$ETL_USER" \
     -v etl_pass="$ETL_DB_PASSWORD" \
     -v db_name="$POSTGRES_DB" <<'EOSQL'

-- ALTER y no CREATE: el rol ya existe desde el script 01 con sus GRANT de
-- lectura. Solo le falta poder iniciar sesión.
SELECT format('ALTER ROLE %I LOGIN PASSWORD %L', :'etl_user', :'etl_pass')
\gexec

GRANT CONNECT ON DATABASE :"db_name" TO :"etl_user";

-- ---------------------------------------------------------------------------
-- No se le concede nada sobre academico_oltp.usuarios (creada en el script 05,
-- posterior al GRANT ... ON ALL TABLES del 01). Es deliberado: esa tabla tiene
-- credenciales de la aplicación y no es un insumo analítico. El Data Warehouse
-- no debe poder leerla.
--
-- Tampoco se le da nada sobre el esquema auditoria por la misma razón.
-- ---------------------------------------------------------------------------

EOSQL

echo "Rol de solo lectura '$ETL_USER' habilitado para conexión."
