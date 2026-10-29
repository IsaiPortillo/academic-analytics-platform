# Correcciones de seguridad — registro de validación

Fecha: 28 de octubre de 2026. Base: volumen local con los datos sintéticos (36 704 inscripciones,
131 872 calificaciones).

Cada hallazgo de la revisión se confirmó en el código o en la base **antes** de corregirlo, y cada
corrección tiene pruebas automatizadas y una comprobación contra la aplicación en ejecución.

## Resumen

| # | Prioridad | Hallazgo | ¿Se confirmó? | Corrección | Pruebas |
|---|---|---|---|---|---|
| 1 | Alta | Un docente podía escribir notas o asistencia en secciones ajenas desde la base | Sí: 0 tablas con RLS; el propio código lo advertía (`calificaciones.py`) | Seguridad por fila en `evaluaciones`, `calificaciones` y `asistencias` (`database/oltp/16_rls_docente.sql`) | `test_rls_docente.py` (13, contra PostgreSQL real) y `test_seguridad.py` (2) |
| 2 | Alta | Tramo Cloudflare → servidor sin cifrar; el servidor respondía por HTTP en su IP pública | Sí: `listen 80` con `server_name` que incluía la IP; el bloque 443 estaba comentado | vhost solo HTTPS con certificado de origen, conexiones que no vienen de Cloudflare cerradas (`deploy/nginx-edumetrics.conf`, `deploy/nginx-minerva-http.conf`) | `nginx -t` y peticiones reales en un contenedor nginx 1.24 |
| 3 | Alta | Sin protección CSRF | Sí: ninguna aparición de «csrf» en `backend/` | Token por sesión exigido en todo `POST` (`app/csrf.py`); cerrar sesión pasa a `POST` | `test_seguridad.py` (13) |
| 4 | Alta | Intentos de login ilimitados | Sí: `procesar_login` sin contador; nginx sin `limit_req` | Bloqueo temporal en la aplicación (`app/limite_login.py`) y `limit_req` en nginx | `test_seguridad.py` (9) |
| 5 | Media | Un usuario desactivado conservaba su sesión durante 14 días | Sí: `activo` solo se leía al iniciar sesión; cookie con `max_age` por defecto | Vigencia revisada en cada petición, 30 min de inactividad, cookie de 8 h (`app/dependencies.py`) | `test_seguridad.py` (7) |
| 10 | Baja | Mensajes de éxito y error en la URL, falsificables | Sí: 32 redirecciones con `?ok=` o `&error=` en 4 routers | Avisos en la sesión, de un solo uso (`app/avisos.py`) | `test_seguridad.py` (4) |

## 1. Seguridad por fila

**Cómo funciona.** Todos los docentes comparten `rol_docente`, así que la aplicación declara en
cada transacción qué docente es, junto al `SET LOCAL ROLE`:

```sql
SELECT set_config('app.docente_id', '<id>', true);   -- local a la transacción
```

Las políticas permiten al docente leer y escribir solo las filas cuyas secciones son suyas. Una
calificación exige además que la inscripción y la evaluación sean **de la misma sección**. El
coordinador y `rol_etl` tienen políticas de acceso completo; el dueño de las tablas no está sujeto a
RLS, así que la auditoría (`SECURITY DEFINER`) sigue igual.

**Falla cerrado.** Sin `app.docente_id`, el docente no ve ninguna fila.

**Límite.** Protege de errores de la aplicación (una consulta sin filtro, un id manipulado en un
formulario). No protege de quien tenga la credencial de `rol_app`, que puede declarar cualquier
docente: esa credencial equivale a la aplicación entera y solo está en el `.env`.

**Rendimiento.** Una primera versión usaba funciones auxiliares con `SET search_path`. PostgreSQL
no puede incorporarlas al plan y las ejecutaba por cada fila: contar las notas visibles tardaba
**26 s**. Con las condiciones escritas en línea, el planificador las resuelve con semi-joins:

| Consulta como docente | Funciones auxiliares | Subconsultas en línea |
|---|---|---|
| `count(*)` de calificaciones | 26 169 ms | 28 ms |
| `count(*)` de asistencias | 9 731 ms | 16 ms |
| Pantalla de calificaciones (petición completa) | — | 54 ms |
| Pantalla de asistencia (petición completa) | — | 74 ms |

**Resultados contra la base real** (`backend/tests/test_rls_docente.py`, transacciones revertidas):

| Intento como docente | Resultado |
|---|---|
| Registrar asistencia en una sección ajena | `new row violates row-level security policy` |
| Crear una evaluación en una sección ajena | rechazado |
| Poner nota en una evaluación ajena | rechazado |
| Cruzar una evaluación propia con un estudiante de otra sección | rechazado |
| Mover una evaluación propia a otra sección (`UPDATE seccion_id`) | rechazado (`WITH CHECK`) |
| `UPDATE` de notas de una evaluación ajena | 0 filas afectadas |
| Leer notas: filas de secciones ajenas visibles | 0 |
| Sin docente declarado: filas visibles en las tres tablas | 0, 0, 0 |
| Registrar asistencia y actualizar notas en su propia sección | permitido |
| Coordinador | ve todas las filas |

**Lo que no cambió.** `rol_etl` sigue leyendo las 131 872 calificaciones y la validación del
almacén da **88 de 88**. Las tablas de evaluaciones y de roster que ve el docente son idénticas a
las que ve el coordinador para la misma sección.

## 2. Cifrado entre Cloudflare y el servidor

El vhost queda así:

- Cualquier petición que no sea para el dominio (por ejemplo, por la IP pública) se cierra sin
  respuesta (444).
- El HTTP del dominio solo redirige a HTTPS.
- El HTTPS usa el certificado de origen de Cloudflare. Una conexión que no viene de un rango de
  Cloudflare se cierra. La comprobación usa la IP que abrió la conexión (`$realip_remote_addr`),
  no la cabecera `CF-Connecting-IP`, que cualquiera puede falsificar.
- `X-Forwarded-For` lleva solo la IP real del visitante, para que el bloqueo de intentos no se
  pueda esquivar cambiando la cabecera.

Comprobado en un contenedor nginx 1.24 con un certificado de prueba:

| Petición | Resultado |
|---|---|
| `nginx -t` con los dos archivos | `syntax is ok` |
| `nginx -t` sin el archivo del contexto http | falla (a propósito: el vhost no arranca sin sus defensas) |
| `http://<IP>/` y `https://<IP>/` | conexión cerrada |
| `https://edumetrics.tech/login` desde fuera de Cloudflare | conexión cerrada |
| Lo mismo con `CF-Connecting-IP` falsificada | conexión cerrada |

**Pendiente en el servidor**, porque no se puede hacer desde el repositorio: crear el certificado
de origen, poner Cloudflare en «Full (strict)», `COOKIE_SECURE=true` y restringir el cortafuegos a
Cloudflare. Los pasos están en la cabecera de `deploy/nginx-edumetrics.conf`.

## 3 a 10. Capa web

Comprobado contra la aplicación en ejecución (22 de 22):

| Comprobación | Resultado |
|---|---|
| Login sin token / con token inventado | 403 |
| Login con token | 303; el token se renueva al iniciar sesión |
| `POST` de costos sin token (coordinador con sesión) | 403 |
| Las 9 rutas `POST` sin token, por ASGI | 403 en todas |
| `GET /logout` | ya no cierra la sesión (no se puede forzar con `<img src>`) |
| URL con `?ok=Tu cuenta fue suspendida` | el texto no aparece en la página |
| Asistencia enviada a una sección ajena | redirige sin mensaje en la URL; el aviso aparece una vez; 0 filas escritas |
| Matrícula por lotes con secciones ya matriculadas | muestra el motivo, no crea inscripciones |
| Desactivar la cuenta del docente con la sesión abierta | el siguiente clic manda al login |
| Reactivarla | la sesión anterior no revive |
| Cookie de sesión | `Max-Age=28800` (8 h) |
| 6 intentos fallidos seguidos | 401 ×5, luego 429 con `Retry-After` |
| Otra cuenta desde la misma IP durante el bloqueo | entra normalmente |

**Cambio de comportamiento en la matrícula.** El dock enviaba una petición por sección con
`fetch` y leía el resultado de la URL. Ahora envía un solo formulario con todas las secciones y el
servidor matricula cada una con su propio punto de guardado: si una falla, las demás se conservan.

**Límite del bloqueo de intentos.** El contador vive en la memoria del proceso: alcanza con el
único worker del despliegue y se reinicia al reiniciar el servicio. El límite de nginx no depende
de él.

## Pruebas

| Suite | Antes | Ahora |
|---|---|---|
| Backend | 132 | 180 (+35 `test_seguridad.py`, +13 `test_rls_docente.py`) |
| Dashboard | 24 | 24 |
| ETL | 47 | 47 |
| **Total** | **203** | **251** |

`test_rls_docente.py` se omite sola si PostgreSQL no está levantado.
