#!/bin/bash
# =============================================================================
# FASE 2 - CREACIÓN DEL USUARIO DE SERVICIO DE LA APLICACIÓN
# =============================================================================
# Se ejecuta automáticamente en el primer arranque del contenedor, después de
# los scripts .sql. Va en un .sh (y no en un .sql) porque la contraseña llega
# por variable de entorno, y los archivos .sql no interpolan el entorno.
# =============================================================================
set -euo pipefail

if [ -z "${APP_DB_PASSWORD:-}" ]; then
    echo "ERROR: APP_DB_PASSWORD no está definida. Revisa tu archivo .env" >&2
    exit 1
fi

APP_USER="${APP_DB_USER:-rol_app}"

psql -v ON_ERROR_STOP=1 \
     --username "$POSTGRES_USER" \
     --dbname "$POSTGRES_DB" \
     -v app_user="$APP_USER" \
     -v app_pass="$APP_DB_PASSWORD" \
     -v db_name="$POSTGRES_DB" <<'EOSQL'

-- Crear el rol de login solo si no existe (idempotente).
-- %I / %L aplican el escapado correcto de identificador y literal.
SELECT format('CREATE ROLE %I LOGIN NOINHERIT PASSWORD %L', :'app_user', :'app_pass')
WHERE NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = :'app_user')
\gexec

-- ---------------------------------------------------------------------------
-- NOINHERIT es deliberado y es la pieza clave del modelo de seguridad:
-- rol_app es MIEMBRO de rol_coordinador y rol_docente, pero NO hereda sus
-- privilegios automáticamente. Debe invocar SET ROLE explícitamente para
-- obtenerlos. Si la aplicación omitiera ese SET ROLE, la sesión se queda SIN
-- permisos, en lugar de quedarse con la unión de ambos roles.
-- El comportamiento por defecto (INHERIT) haría exactamente lo contrario.
-- ---------------------------------------------------------------------------
GRANT rol_coordinador TO :"app_user";
GRANT rol_docente     TO :"app_user";

-- Privilegios directos mínimos: leer la tabla de usuarios para poder
-- autenticar ANTES de saber a qué rol hay que cambiar.
GRANT CONNECT ON DATABASE :"db_name" TO :"app_user";
GRANT USAGE ON SCHEMA academico_oltp TO :"app_user";
GRANT SELECT ON academico_oltp.usuarios TO :"app_user";

EOSQL

echo "Rol de servicio '$APP_USER' creado y configurado."
