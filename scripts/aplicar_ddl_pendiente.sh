#!/usr/bin/env bash
# =============================================================================
# UNIVERSIDAD DE EL SALVADOR - FACULTAD MULTIDISCIPLINARIA ORIENTAL
# APLICAR LOS SCRIPTS DDL QUE LE FALTEN A UNA BASE YA CREADA
# =============================================================================
# Los scripts de database/oltp/ se ejecutan AUTOMÁTICAMENTE, pero solo en el
# primer arranque sobre un volumen vacío. Si alguien del equipo agrega un script
# nuevo, a los demás no les llega: el contenedor ya existe y Docker no vuelve a
# correr nada. El síntoma es una pantalla que devuelve 500 con
# «relation "..." does not exist», y cuesta media hora averiguar por qué a un
# compañero le funciona y a vos no.
#
# Este script detecta qué falta y lo aplica. No lleva un registro de migraciones:
# para cada script pregunta a la base si el objeto que crea ya existe. Es más
# simple y funciona sobre las bases que ya existían antes de que esto se
# escribiera, que son justamente las que tienen el problema.
#
#   ./scripts/aplicar_ddl_pendiente.sh            # aplica lo que falte
#   ./scripts/aplicar_ddl_pendiente.sh --revisar  # solo informa, no cambia nada
#
# Después de aplicar algo del Data Warehouse hay que recargarlo:
#   python -m etl.carga
# =============================================================================

set -euo pipefail

RAIZ="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CONTENEDOR="academico_postgres"
SOLO_REVISAR=0
[[ "${1:-}" == "--revisar" ]] && SOLO_REVISAR=1

cd "$RAIZ"

if [[ ! -f .env ]]; then
    echo "ERROR: no existe .env en la raíz. Copia .env.example y complétalo." >&2
    exit 1
fi
set -a; . ./.env; set +a

if ! docker exec "$CONTENEDOR" pg_isready -q 2>/dev/null; then
    echo "ERROR: el contenedor $CONTENEDOR no responde." >&2
    echo "       Levanta los motores con: docker compose up -d" >&2
    exit 1
fi

# Cada script con la consulta que responde «¿ya está aplicado?». Deben devolver
# una fila si el objeto existe y ninguna si no. El orden importa: es el mismo en
# que Docker los ejecutaría.
SCRIPTS=(
  "01_init_oltp_academico.sql|SELECT 1 FROM pg_tables WHERE schemaname='academico_oltp' AND tablename='inscripciones'"
  "05_usuarios_auth.sql|SELECT 1 FROM pg_tables WHERE schemaname='academico_oltp' AND tablename='usuarios'"
  "06_bootstrap_rol_app.sh|SELECT 1 FROM pg_roles WHERE rolname='rol_app' AND rolcanlogin"
  "07_bootstrap_rol_etl.sh|SELECT 1 FROM pg_roles WHERE rolname='rol_etl' AND rolcanlogin"
  "08_costos_institucionales.sql|SELECT 1 FROM pg_tables WHERE schemaname='academico_oltp' AND tablename='costos_uv'"
  "09_fix_auditoria_security_definer.sql|SELECT 1 FROM pg_proc WHERE proname='fn_auditoria_cambio_nota' AND prosecdef"
  "10_dw_academico.sql|SELECT 1 FROM pg_tables WHERE schemaname='dw_academico' AND tablename='fact_inscripcion'"
  "11_bootstrap_rol_dashboard.sh|SELECT 1 FROM pg_roles WHERE rolname='rol_dashboard' AND rolcanlogin"
  "12_dw_diagnostico.sql|SELECT 1 FROM pg_indexes WHERE schemaname='dw_academico' AND indexname='idx_fact_patron_riesgo'"
  "13_dw_cierre_scrum35.sql|SELECT 1 FROM pg_views WHERE schemaname='dw_academico' AND viewname='v_mart_departamento'"
  "14_bootstrap_rol_dw_carga.sh|SELECT 1 FROM pg_roles WHERE rolname='rol_dw_carga' AND rolcanlogin"
  "15_dw_red_curricular.sql|SELECT 1 FROM pg_tables WHERE schemaname='dw_academico' AND tablename='bridge_prerrequisito'"
  "16_rls_docente.sql|SELECT 1 FROM pg_policies WHERE schemaname='academico_oltp' AND tablename='calificaciones' AND policyname='docente_propias'"
  "17_auditoria_y_actas.sql|SELECT 1 FROM pg_trigger WHERE tgname='trg_bloquear_acta' AND tgrelid='academico_oltp.calificaciones'::regclass"
  "18_usuarios_cuenta.sql|SELECT 1 FROM pg_proc WHERE proname='cambiar_password_propio'"
  "19_motivo_retiro.sql|SELECT 1 FROM information_schema.columns WHERE table_schema='academico_oltp' AND table_name='inscripciones' AND column_name='motivo_retiro'"
  "20_metas_indicadores.sql|SELECT 1 FROM pg_views WHERE schemaname='dw_academico' AND viewname='v_semaforo_indicador'"
  "21_perfil_propio.sql|SELECT 1 FROM pg_proc WHERE proname='actualizar_perfil_propio'"
)

consultar() {
    docker exec -e PGPASSWORD="$POSTGRES_PASSWORD" "$CONTENEDOR" \
        psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -tAc "$1" 2>/dev/null
}

aplicar_sql() {
    docker exec -i -e PGPASSWORD="$POSTGRES_PASSWORD" "$CONTENEDOR" \
        psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -q -v ON_ERROR_STOP=1 < "database/oltp/$1"
}

aplicar_sh() {
    # Los bootstrap de roles leen sus credenciales del entorno, no del .env:
    # corren dentro del contenedor, que no tiene el archivo.
    docker exec -i -e PGPASSWORD="$POSTGRES_PASSWORD" \
        -e POSTGRES_USER -e POSTGRES_DB \
        -e APP_DB_USER -e APP_DB_PASSWORD \
        -e ETL_DB_USER -e ETL_DB_PASSWORD \
        -e DASHBOARD_DB_USER -e DASHBOARD_DB_PASSWORD \
        -e DASHBOARD_USER="${DASHBOARD_USER:-${DASHBOARD_DB_USER:-}}" \
        -e DW_CARGA_DB_USER -e DW_CARGA_DB_PASSWORD \
        "$CONTENEDOR" bash -s < "database/oltp/$1"
}

echo "Revisando los scripts de database/oltp/ contra $POSTGRES_DB"
echo

faltan=0
aplicados=0
toca_dw=0

for entrada in "${SCRIPTS[@]}"; do
    archivo="${entrada%%|*}"
    comprobacion="${entrada#*|}"

    if [[ ! -f "database/oltp/$archivo" ]]; then
        printf "  %-42s %s\n" "$archivo" "NO ESTÁ EN EL REPOSITORIO"
        continue
    fi

    if [[ -n "$(consultar "$comprobacion")" ]]; then
        printf "  %-42s ya aplicado\n" "$archivo"
        continue
    fi

    faltan=$((faltan + 1))
    [[ "$archivo" == 1[0-5]_* || "$archivo" == 20_* ]] && toca_dw=1

    if (( SOLO_REVISAR )); then
        printf "  %-42s FALTA\n" "$archivo"
        continue
    fi

    printf "  %-42s aplicando... " "$archivo"
    salida=$(mktemp)
    if { [[ "$archivo" == *.sh ]] && aplicar_sh "$archivo" || [[ "$archivo" == *.sql ]] && aplicar_sql "$archivo"; } >"$salida" 2>&1; then
        echo "listo"
        aplicados=$((aplicados + 1))
    else
        echo "FALLÓ"
        sed 's/^/      /' "$salida" | tail -6
        rm -f "$salida"
        echo
        echo "Se detuvo en $archivo. Los scripts posteriores pueden depender de él." >&2
        exit 1
    fi
    rm -f "$salida"
done

echo
if (( faltan == 0 )); then
    echo "Tu base está al día: no falta ningún script."
elif (( SOLO_REVISAR )); then
    echo "Faltan $faltan script(s). Ejecuta el comando sin --revisar para aplicarlos."
else
    echo "Aplicados $aplicados script(s)."
    if (( toca_dw )); then
        echo
        echo "Se tocó el Data Warehouse, así que hay que recargarlo para poblar lo nuevo:"
        echo "    python -m etl.carga"
    fi
fi
