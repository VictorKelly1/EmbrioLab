# Áreas de mejora pendientes

Revisión del 2026-11-12, después de las semanas 1–8 y de los cambios del cliente. Lo hecho
se tacha o se borra en el PR que lo resuelve. Las decisiones de negocio pendientes están en
`CONTEXTO.md` §8; aquí solo va lo técnico.

**Ya resuelto:** CI con protección de `main` y matriz de permisos (PR #22); formularios desde
archivos JSON con revisión y vista previa (PR #23).

## Frontend (desarrollador de UI)

Reglas y límites en `AGENTS.md`, «Si tu tarea es solo el frontend».

- **Sacar el JavaScript de las plantillas.** Hay bloques `<script>` en 10 plantillas
  (`app.html`, `citas/agendar.html`, `citas/calendario.html`, `citas/detalle.html`,
  `citas/_selector_paciente.html`, `cotizaciones/cotizar.html`, `cuentas/entrar.html`,
  `formularios/publico.html`, `pedidos/crear.html`, `pedidos/_linea_script.html`) y algunos
  `onclick=`. Deben pasar a archivos en `static/js/` con `data-` atributos. Es requisito para
  activar CSP (ver «Seguridad»).
- **Páginas de error propias:** `templates/403.html`, `404.html` y `500.html` (la 500 sin
  lógica ni contexto). Hoy salen las de Django.
- **Dividir el CSS** (`static/css/embriolab.css`, ~2,700 líneas) por secciones o componentes,
  sin herramientas de compilación.
- **Más HTMX** donde hoy se recarga la página completa: tomar/soltar paciente, agregar
  observaciones, cambiar el pago. Si hace falta que la vista responda un fragmento, se pide.
- **Diseño responsivo y pulido general** de todas las pantallas (incluye revisar a 390 px).

## Backend

- **Dividir `apps/pedidos`.** `services.py` (~460 líneas) y `views.py` (~510) mezclan armado
  del pedido, toma por paciente, captura, pagos y envío: separarlos en módulos sin cambiar
  el comportamiento.
- **Un solo manejo de errores en las vistas.** 17 vistas repiten `try/except ValidationError`
  y el mensaje se arma en 5 lugares: un mixin en `core` para «llamar al servicio, avisar y
  redirigir».
- **Regla única para `usuario` en los servicios** (hoy es obligatorio en unos y opcional en
  otros, con `None` = automático).
- **Paginación** en la lista de formularios llenados y en las listas de envíos (si el
  frontend necesita el fragmento, se coordina).
- **Bandeja de envíos fallidos** para reintentarlos sin buscar cita por cita.
- **Worker:** healthcheck y aviso si hay notificaciones pendientes por mucho tiempo (ya se
  cayó una vez sin que se notara). En desarrollo no recarga solo el código.
- **Logs y errores:** logging mínimo hoy; falta aviso de errores 500 (correo a los admins o
  un servicio externo).
- **`demo.py`** simula la hora con `unittest.mock`: solo desarrollo, pero conviene aislarlo.

## Seguridad (bloque de la semana 9; se usarán skills de seguridad)

- **Sesiones:** hoy duran 2 semanas (valor de Django). Caducidad por inactividad y al cerrar
  el navegador.
- **CSP** con el soporte de Django 6 (después de sacar el JS de las plantillas).
- **Admin de Django** en `/admin/`: moverlo a una URL no obvia (CONTEXTO.md §5).
- **Doble factor (2FA)**, al menos para el admin y los químicos.
- **Gestión de usuarios:** restablecer contraseña y dar de baja desde el sistema (pregunta
  abierta en CONTEXTO.md §8).
- **Auditoría** con `django-auditlog` (pacientes, resultados, pagos). También unificaría el
  «quién hizo qué», hoy repartido en varios campos.
- **Respaldos cifrados** de PostgreSQL.
- **HSTS preload** (`security.W021`, tolerado en la CI): decidir con el cliente cuando haya
  dominio.
- **Repositorio privado.** Al hacerlo privado, la protección de `main` deja de aplicar en una
  cuenta gratuita (requiere GitHub Pro).
