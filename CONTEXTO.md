# CONTEXTO — EmbrioLab (Fase 1)

> Documento de referencia para desarrolladores y agentes de IA que trabajen en este repositorio.
> **Léelo completo antes de escribir código.** Contiene las decisiones de negocio, el diseño de la base de datos, la arquitectura y el plan de trabajo de 10 semanas.
> Si algo de aquí contradice al código, manda este documento: consulta antes de cambiar una decisión (ver §9).

Última actualización: 2026-11-11

---

## 1. El problema

EmbrioLab es un laboratorio clínico. Sus categorías de estudios son **Sanguíneos, Esperma, Cultivo y Otros**.

Hoy todo se hace a mano:
1. La recepción agenda la cita.
2. El paciente llega con la orden del doctor y llena un formulario (en papel o en Google Forms). El formulario depende de si es hombre o mujer.
3. La recepcionista pasa los datos a un Excel que usan como "base de datos".
4. Sube los formularios a una carpeta compartida.
5. Los químicos descargan los formularios y llenan los estudios, lo que puede tardar días o meses.
6. Los resultados se mandan a mano por correo o WhatsApp.

Resultado: errores y anomalías. La **Fase 1** reemplaza este flujo con un sistema web en Django.

## 2. Roles y alcance de la Fase 1

Un usuario tiene **un solo rol**, pero la BD está normalizada para permitir varios en el futuro. Hay **una sola sucursal**.

| Rol | Qué hace |
|---|---|
| **Paciente** | Es una entidad del sistema, **sin acceso**. Recibe un recordatorio de su cita 24 h antes y un link/QR para llenar su formulario. Recibe sus resultados. |
| **Recepcionista** | Agenda citas desde un calendario, a pacientes registrados o **sin registro** (y registra al paciente cuando llega). Registra, edita, busca y da de baja lógica a pacientes. Marca la cita como atendida o no atendida y envía el QR del formulario. Arma **cotizaciones** de un conjunto de estudios (ver §3). Arma los **pedidos** (relaciona el nombre que dio el doctor con el catálogo de estudios, usando alias) y les agrega **observaciones**. **No asigna químicos:** los estudios quedan en la cola de los químicos. Registra el estado de pago. |
| **Químico** | **Toma pacientes de la «Cola de pedidos»**: al tomar a un paciente se queda con todos sus estudios pendientes, de todos sus pedidos. Ve **todos** los pedidos, actuales e históricos, **con filtros** (por químico encargado, estado, paciente, fecha…). Captura resultados; el sistema hace los cálculos internos. Completa estudios y envía los resultados, uno por uno o en conjunto, al paciente y, si se elige, al doctor del pedido. Consulta al paciente y el catálogo. **Ve, registra y edita doctores.** **Ve el calendario de citas en solo lectura** (no agenda ni cambia citas). |
| **Administrador** | En la Fase 1: registro de usuarios y reportes generales. Los reportes se definirán cuando el cliente los entregue. |

**Fuera de la Fase 1** (dejar preparado, NO implementar):
- Editor de formularios para la recepcionista.
- Creación de estudios por el admin.
- Abonos con monto.
- Donadores (pendiente de información del cliente).
- Multi-sucursal.
- Integración real con la API de WhatsApp.

## 3. Reglas de negocio

### Citas
- Cada cita dura **30 minutos fijos**.
- **No puede haber dos citas empalmadas** (hay un solo horario de atención). Valídalo en el servicio **y** en la BD con un `ExclusionConstraint` sobre el rango `[fecha_hora, fecha_fin)`, para que sea seguro aunque haya concurrencia. `fecha_fin` se guarda porque `timestamptz + interval` no es inmutable en PostgreSQL y no puede ir en el índice; un `CHECK` garantiza que sea `fecha_hora + 30 min`.
- **Estados:** `programada`, `atendida`, `no_atendida`. Reprogramar = cambiar `fecha_hora`.
- **Las canceladas se BORRAN** (no se guardan).
- Se puede atender a alguien **sin cita**: se crea una cita con `origen = espontanea` (con paciente registrado).
- **Cita sin registro:** se puede agendar sin registrar al paciente. La cita guarda solo nombre, apellido paterno, género (para elegir el formulario) y teléfono o correo (para el recordatorio y el link). Cuando llega, la recepción **registra su llegada**: elige al paciente si ya existe o lo registra en ese momento; la cita queda ligada a él, con su folio, y atendida. Si no llega, queda «no atendida» sin crear paciente. Un `CHECK` exige paciente en una cita atendida y los datos mínimos en una sin paciente.
- El recordatorio sale **24 h antes** y queda marcado con `recordatorio_enviado`.

### Folio
- Se forma con las **2 primeras letras del apellido paterno + 2 del materno + el número de paciente**.
- Es el mismo en **todas las citas del mismo paciente** (así lo maneja el cliente) y el paciente lo ve.
- Pendiente: la regla para quien no tiene apellido materno. **La decide el cliente.** Mientras tanto, déjala aislada en una sola función.

### Pacientes
- Se registran **una sola vez**, con sus datos fijos.
- **CURP obligatoria y única.** INE opcional. Género: `masculino` / `femenino`.
- **Correo o WhatsApp obligatorio:** al registrar y al editar, el paciente debe tener al menos uno de los dos (el teléfono no cuenta), para poder enviarle sus resultados. Lo revisa el servicio.
- **Nunca se eliminan:** borrado lógico (inactivo).
- Un paciente puede tener varios pedidos abiertos a la vez.

### Formulario por QR
- Trae **solo preguntas que cambian en cada visita** (días de abstinencia, enfermedades recientes…), nunca datos de identidad.
- Se accede con un **link con token único**, que **caduca**, es **de un solo uso** y sirve solo para esa cita.
- El formulario se elige según el género del paciente.

### Pedidos y estudios
- Una cita puede tener **varios pedidos** (1:N). Un pedido tiene N estudios (tabla EstudiosPedido).
- **Estados de un estudio:** `pendiente → en_proceso → completado`.
  - "Enviado" = `fecha_envio` no nula, y **solo es posible después de completado**.
  - **Un estudio completado se puede corregir mientras no se envíe**; ya enviado, no cambia. Lo corrige su químico encargado volviendo a capturar todos los campos (se recalcula y se vuelve a copiar la referencia).
  - **Cola de químicos (por paciente):** un estudio `pendiente` no tiene encargado y espera en la cola, que se agrupa por paciente. Un químico **toma al paciente**: todos sus estudios pendientes, de todos sus pedidos, pasan a `en_proceso` con él como **único encargado** (se guarda en cada estudio).
  - Mientras el paciente tenga estudios en proceso, ese químico es su encargado: los estudios que se le agreguen después (al pedido o en un pedido nuevo) **quedan a su cargo automáticamente**. Otro químico no puede tomarlo.
  - El encargado puede **soltar al paciente** (sus estudios en proceso vuelven a la cola) o **pasarlo** a otro químico, solo mientras no haya capturado nada de ninguno.
  - La lista de trabajo del químico son los estudios `en_proceso` a su cargo.
- Un pedido está **completado** cuando todos sus estudios están completados **y** enviados, estén pagados o no.
- `Pedido.estado`, `Pedido.estado_pago` y `Pedido.total_pago` son **derivados**. Se guardan en la tabla, pero **solo los actualiza un servicio** (ver §6).
- Se registra **quién lo tomó (y cuándo), quién lo completó y quién lo envió**.
- No hay validador aparte: el químico es el responsable.

### Pagos
- El pago es **por estudio**, con 3 estados: `pagado`, `abonado`, `pendiente`.
- **El envío de resultados NO depende del pago.**
- Los abonos con monto son de una fase posterior. Por ahora solo se guarda el estado, pero **`estado_pago` se cambia exclusivamente desde un servicio**, para poder conectar después la tabla `Abonos`.

### Almacenamiento de formularios y resultados
- Solo se guarda **JSON**. **No se almacenan PDFs:** el PDF se genera al vuelo.

### Estudios
- Son **~30 estudios fijos, definidos en código**, porque tienen cálculos internos. El cliente entrega un Excel con sus campos, operaciones y claves.
- No hay paquetes de estudios guardados. Para cotizar se arma un **paquete temporal** (ver «Cotizaciones»).
- La recepcionista guarda **alias**: el nombre que usa el doctor → el estudio del catálogo.

### Cotizaciones
- La recepción elige un conjunto de estudios (un paquete temporal) y obtiene el total con los **precios vigentes**. También puede agregar **estudios que no están en el catálogo**, escribiendo su nombre, su precio y, si quiere, su categoría (por omisión «Otros»); no se agregan al catálogo.
- **No se guarda en la BD:** es una función (`apps/cotizaciones/cotizacion.py`). El PDF se genera al vuelo.
- Se descarga en PDF o se **envía** por correo y WhatsApp a un paciente registrado o a un correo/WhatsApp escrito a mano (para quien no está registrado).
- El envío sale **directo**, sin fila en `Notificaciones` ni worker (decidido con el cliente): si un canal falla, la recepción ve el error y puede reintentar o descargar el PDF.

### Valores de referencia
- El cliente los cambia seguido, a veces se los proporcionan terceros y varían por estudio. Por eso van **en la BD** y no en código. La tabla es **provisional**.
- Al completar un estudio, la referencia que se usó **se copia dentro del JSON de resultados**.

### Notificaciones
- Se envían por **correo y WhatsApp**. Los resultados van al paciente y, si el químico lo elige, también al doctor del pedido. La API de WhatsApp se integra después: deja la abstracción lista.
- Todo envío queda registrado en la tabla `Notificaciones`, **excepto las cotizaciones** (ver abajo).

## 4. Base de datos

Los nombres del E-R usan la convención del diseño original. **En Django:** modelos en singular y campos en `snake_case` (`Paciente.apellido_paterno`). Si hace falta, usa `db_table` para conservar los nombres de tabla. Los `Id*` son FK.

### Personas y usuarios
| Tabla | Campos |
|---|---|
| **Direcciones** | Id, Calle, Numero, ColoniaFrac, Ciudad, Estado, Pais, CodigoPostal. *Sin propietario: se puede compartir.* |
| **Personas** | Id, IdDireccion (null), Nombre, ApellidoPaterno, ApellidoMaterno, Genero, FechaNacimiento, NumeroINE (null), CURP (unique), Foto (null, almacenamiento privado) |
| **Contactos** | Id, IdPersona, Tipo (telefono/correo/whatsapp…), Valor, Principal |
| **Usuarios** | Id, IdPersona (unique, 1:1), NombreUsuario (null, provisional), Correo (unique, **login**), Contrasena (hash), Color. **= modelo de usuario personalizado de Django** |
| **Admins / Recepcionistas** | Id, IdUsuario (unique), EstadoActividad, FechaRegistro, Sueldo |
| **Quimicos** | Igual que las anteriores + CedulaProfesional |

### Pacientes
| Tabla | Campos |
|---|---|
| **Pacientes** | Id, IdPersona (unique), Numero (unique), EstadoActividad, FechaRegistro |
| **Doctores** | Id, Nombre, Correo, WhatsApp (al menos uno de los dos; lo exige el servicio), Contacto (otros datos en texto libre) |
| **Donadores** | ⏸ PENDIENTE (falta información del cliente). Es un tipo especial de paciente con un inventario de muestras de esperma: código, fecha, disponible/usada y doctor al que se envió. **No implementar.** |

### Citas y formularios
| Tabla | Campos |
|---|---|
| **Citas** | Id, IdRecepcionista, IdPaciente (null = sin registro), Nombre, ApellidoPaterno, Genero, Telefono, Correo (los de quien agenda sin registro), FechaHora, FechaFin (= FechaHora + 30 min, la calcula el modelo), Asunto, Estado, Origen (agendada/espontanea), NumeroFolio, TokenQR (**hash**), TokenExpiracion, RecordatorioEnviado |
| **Formularios** | Id, Nombre, Descripcion, GeneroAplicable (null = todos), Activo, FechaCreacion, IdUsuarioCreador (null) |
| **VersionesFormulario** | Id, IdFormulario, NumeroVersion, Esquema (JSON), Publicada, FechaPublicacion. *Índice único parcial: solo una versión publicada por formulario.* |
| **FormulariosLlenados** | Id, IdCita, **IdVersionFormulario**, Respuestas (JSON), FechaLlenado |

### Estudios
| Tabla | Campos |
|---|---|
| **CategoriasEstudio** | Id, Nombre |
| **Estudios** | Id, Clave (unique, la da el cliente; enlaza con la clase en código), Nombre, IdCategoria, Precio (vigente), VersionDefinicion, Activo |
| **EstudioAlias** | Id, IdEstudio, Alias (unique, normalizado sin acentos ni mayúsculas), IdUsuarioRegistro, FechaRegistro |
| **ValoresReferencia** *(provisional)* | Id, IdEstudio, ClaveCampo, Genero (null), EdadMinima/EdadMaxima (null), ValorMinimo/ValorMaximo (null), TextoReferencia (null), Unidad, Activo, VigenteDesde, IdUsuarioRegistro |

### Pedidos
| Tabla | Campos |
|---|---|
| **Pedidos** | Id, IdCita, IdRecepcionista, IdDoctor (null), Numero, FechaInicio, Estado\*, EstadoPago\*, TotalPago\*, FechaCompletado, FechaEnvio. *(\* derivados)* |
| **EstudiosPedido** | Id, IdPedido, IdEstudio, NombreSolicitado, Precio (copia al momento del pedido), **VersionEstudio**, Estado, EstadoPago, Resultados (JSON), **IdQuimicoEncargado (null), FechaToma (null)**, IdQuimicoCompleto, FechaCompletado, IdUsuarioEnvio, FechaEnvio. *Un `CHECK` exige: pendiente sin encargado, en proceso con encargado.* |
| **ObservacionesPedido** | Id, IdPedido, Texto (hasta 500 caracteres), IdUsuario, Fecha. *Notas libres de la recepción; un pedido tiene las que hagan falta.* |
| **Abonos** | ⏸ FASE POSTERIOR, no crear. Diseño previsto: Id, IdEstudioPedido, Monto, Fecha, MetodoPago, IdRecepcionista |

### Notificaciones
| Tabla | Campos |
|---|---|
| **Notificaciones** | Id, Tipo (recordatorio/qr/resultados), Canal (correo/whatsapp), Destinatario, DestinoTipo (paciente/doctor), IdCita (null), IdEstudioPedido (null), Estado (pendiente/enviado/fallido), Error, FechaEnvio |

### Índices mínimos
- `Citas(fecha_hora)`
- `EstudiosPedido(estado)` (los estudios de un químico se buscan por el índice de la FK `quimico_encargado`)
- Trigram (`pg_trgm`) sobre el nombre completo de la persona
- Único parcial en la versión publicada de cada formulario

## 5. Arquitectura

**Monolito modular en Django 6.1 / Python 3.12.**
- Una sola aplicación, dividida en apps por dominio con límites claros.
- Multi-sucursal futura = un despliegue por sucursal, cada uno con su propia BD.

### Stack
| Pieza | Elección |
|---|---|
| BD | **PostgreSQL** (JSONB, índices parciales, `pg_trgm`) |
| Frontend | **Plantillas de Django + HTMX**, sin SPA |
| Tareas en segundo plano | API `django.tasks` + worker respaldado en la BD. Los recordatorios periódicos se lanzan con un comando de gestión programado (cron o timer) que encola tareas. Se puede migrar a Celery sin tocar los servicios |
| PDF | WeasyPrint (HTML → PDF, al vuelo) |
| Despliegue | Docker Compose: nginx + gunicorn + worker + postgres. **El hosting está por definirse (lo decide el cliente).** |
| Pruebas | pytest-django + factory_boy |
| Calidad | ruff (lint + formato) |

### Estructura
```
embriolab/                 # paquete del proyecto
  settings/  base.py · dev.py · prod.py
apps/
  core/            modelos base (timestamps, borrado lógico), mixin RolRequerido, utilidades
  cuentas/         Usuario (AUTH_USER_MODEL), Admin, Recepcionista, Quimico, login
  personas/        Persona, Direccion, Contacto
  pacientes/       Paciente, Doctor  (Donador: pendiente)
  citas/           Cita, calendario, token QR, recordatorios
  formularios/     Formulario, VersionFormulario, FormularioLlenado, render desde el esquema
  estudios/        CategoriaEstudio, Estudio, EstudioAlias, ValorReferencia
    definiciones/  una clase de Python por estudio + registro
  pedidos/         Pedido, EstudioPedido, estados, pagos
  notificaciones/  Notificacion, canales, tareas
  documentos/      PDF de resultados y de cotizaciones
  cotizaciones/    sin modelos: cotizar() + envío directo
templates/ · static/
```

### Capas dentro de cada app
| Archivo | Responsabilidad |
|---|---|
| `models.py` | Datos + restricciones en la BD (`unique`, `CheckConstraint`, índices) |
| `services.py` | **La ÚNICA forma de escribir.** Reglas de negocio dentro de `transaction.atomic` |
| `selectors.py` | Lecturas optimizadas (`select_related` / `prefetch_related`, filtros) |
| `views.py` | Solo HTTP: validan el form, llaman a un servicio y responden. **Nunca modifican modelos directamente.** |

### Patrones
- **Registro + Strategy para los estudios.** Cada estudio es una clase `DefinicionEstudio` con `clave`, `version`, `campos` y `calcular(valores, paciente)`, registrada con `@registrar`. Un **system check** de Django falla si una `Clave` de la BD no tiene clase o una clase no tiene fila en la BD. Los cálculos se prueban con **los ejemplos reales del Excel del cliente**.
- **Máquina de estados** en EstudioPedido. Las transiciones inválidas lanzan una excepción en el servicio.
- **Servicio único para los derivados del pedido y los pagos:** `recalcular_pedido(pedido)` se llama tras cualquier cambio en sus estudios.
- **Outbox de notificaciones:**
  1. El servicio crea la fila `Notificacion(pendiente)` en la misma transacción.
  2. `transaction.on_commit` encola la tarea.
  3. El worker envía, marca `enviado` o `fallido` y reintenta.
- **Adapter por canal:** `CanalCorreo` (SMTP) y `CanalWhatsApp`, que por ahora es un stub que solo registra el envío. Comparten la misma interfaz.
- **Formularios dinámicos:** el `Esquema` JSON se valida al guardar, y un constructor genera el `forms.Form` a partir de él. Los 2 formularios de la Fase 1 se cargan con una **migración de datos** y usan este mismo mecanismo.

### Seguridad (obligatorio)
- **El usuario personalizado va en la PRIMERA migración.** No correr `migrate` antes de tener `AUTH_USER_MODEL`.
- Contraseñas con Argon2; `django-axes` para bloquear tras intentos fallidos.
- `RolRequerido(...)` en **cada** vista, más controles por objeto.
- **Token QR:**
  - Se genera con `secrets.token_urlsafe(32)` y en la BD **solo se guarda su hash**.
  - Tiene expiración, es de un solo uso y el endpoint tiene rate limiting.
  - La página pública no muestra datos del paciente.
- **Auditoría** (`django-auditlog`) de pacientes, resultados y pagos. Son datos de salud: LFPDPPP y NOM-004.
- **Producción:**
  - HTTPS, HSTS, cookies `Secure`/`HttpOnly` y `DEBUG=False`.
  - Secretos en `.env`.
  - El admin de Django en una URL no obvia y solo para el rol admin.
  - `manage.py check --deploy` sin advertencias.
- Media privada (fotos) y respaldos cifrados de PostgreSQL.
- Localización: `LANGUAGE_CODE = 'es-mx'`. La zona horaria es la del laboratorio (confirmar la ciudad con el cliente) y `USE_TZ = True`.

## 6. Plan de 10 semanas

Cada semana termina con un **PR a `main`** que nosotros revisamos. Cada entregable debe tener pruebas.

| Sem | Objetivo | Entregables |
|---|---|---|
| **1** | Cimientos | Settings base/dev/prod; PostgreSQL + Docker Compose; `es-mx`/TZ; ruff + pytest; `core` (modelos base, borrado lógico, `RolRequerido`); `cuentas` con el usuario personalizado y las 3 tablas de rol; modelos `Persona` y `Direccion` (adelantados de la semana 2 porque `Usuario` depende de `Persona`); comando `crear_admin`; login/logout; layout base + HTMX; Argon2 + axes |
| **2** | Personas y pacientes | `personas` (`Contacto`, `Persona.foto`, selectores) y `pacientes` (modelos + servicios + selectores); CRUD de pacientes para la recepcionista; búsqueda por nombre (trigram) y CURP; borrado lógico; número de paciente y **función de folio**; Doctores; el admin registra usuarios con rol |
| **3** | Citas | Modelo Cita con restricción contra empalmes; calendario (vista día/semana) para agendar y ver las próximas; reprogramar; cancelar = borrar; cita espontánea; marcar atendida/no atendida; generación del token QR (hash, expiración, un solo uso) |
| **4** | Formularios | Formularios + versiones + validador del esquema; constructor de forms dinámicos; **migración de datos con los 2 formularios del cliente**; página pública del QR (rate limit, token de un uso); FormularioLlenado; la recepcionista ve las respuestas |
| **5** | Catálogo de estudios | Modelos de estudios, alias y valores de referencia; **registro de definiciones + system check**; carga del catálogo (claves, nombres, precios) desde el Excel del cliente; CRUD de alias y de valores de referencia; primeras definiciones con pruebas contra ejemplos del Excel |
| **6** | Pedidos (recepción) | Armar el pedido desde una cita; relacionar el nombre solicitado con un estudio (sugerencias por alias y guardado de alias nuevos); asignar uno o varios químicos; estado de pago por estudio; servicio `recalcular_pedido`; máquina de estados |
| **7** | Químico | Lista de todos los pedidos **con filtros** (asignado, estado, paciente, fecha, pago); detalle del pedido y del paciente; captura de resultados con un form generado desde la definición; cálculos; completar (con copia de la referencia); historial. Continuar con las definiciones de estudios |
| **8** | Resultados y notificaciones | PDF al vuelo (WeasyPrint); tabla Notificaciones + outbox + worker (aquí se agrega el servicio `worker` a Docker Compose); canal de correo (SMTP) y stub de WhatsApp; envío de resultados individual o en conjunto; recordatorios de 24 h (comando programado); envío del QR |
| **9** | Cierre funcional y endurecimiento | **Terminar las ~30 definiciones de estudios**; auditoría; settings de producción + `check --deploy` (incluye decidir HSTS preload con el cliente cuando haya dominio, y HTTPS en nginx); respaldos; reportes básicos del admin (según lo que entregue el cliente); pulir la interfaz; revisar consultas N+1 e índices |
| **10** | Pruebas y entrega | Pruebas de extremo a extremo del flujo completo (cita → QR → pedido → resultados → envío); **validar los cálculos con el cliente usando casos reales**; pruebas de aceptación con la recepcionista y los químicos; corrección de bugs; despliegue en staging; manual breve de uso |

### Lo que el cliente debe entregar (riesgos del calendario)
| Qué | Se necesita para |
|---|---|
| Los 2 formularios (preguntas, tipos, opciones) | Semana 4 |
| Excel de estudios: claves, campos, fórmulas, precios y ejemplos | Semana 5 (las definiciones continúan hasta la semana 9) |
| Valores de referencia | Semana 5 |
| Regla del folio sin apellido materno | Antes de la semana 9 |
| Reportes del admin | Semana 9 |
| Cuenta SMTP / dominio de correo | Semana 8 |
| Ciudad (zona horaria) y hosting | Zona horaria: cuando se sepa (hay una provisional). Hosting: semana 10 |

## 7. Convenciones

- El código del dominio va **en español** (modelos, servicios, campos) y los commits también.
- Una rama por semana o funcionalidad (`sem-03-citas`), con PR a `main` y revisión antes de hacer merge.
- **No hay merge sin pruebas** de los servicios y de las definiciones de estudios.
- Nada de lógica de negocio en las vistas ni en los templates.
- Las dependencias nuevas se fijan con versión en `requirements.txt`.
- Nunca subir `.env`, credenciales ni datos reales de pacientes al repo.

## 8. Preguntas abiertas

Las decide el cliente. Mientras no responda, el código usa el valor provisional indicado, aislado para cambiarlo fácil.

### Generales
- La **zona horaria** del laboratorio (todavía no se sabe; usar `America/Mexico_City` de forma provisional y dejarla configurable por `.env`).
- El formato del **número de pedido**. Provisional: año y consecutivo anual (`2026-0001`), en `apps/pedidos/numero.py`.
- El diseño de Donadores (falta información del cliente).
- Los reportes del admin (los define el cliente).

### Pacientes y folio (semana 2)
- **Folio sin apellido materno.** Provisional: se rellena con `XX` (`López` → `LOXX15`), como la CURP. Está en `apps/pacientes/folio.py`.
- **Detalles del folio.** Provisional: sin acentos (`Ñ` → `N`), solo letras (`de la Cruz` → `DE`), número sin ceros a la izquierda y `X` si un apellido tiene una sola letra.
- **Número de paciente.** Provisional: empieza en 1. Si el cliente trae números de su Excel, al importarlos se ajusta la secuencia con `setval`.
- **Persona que ya existe en el sistema** (por ejemplo, un empleado que se registra como paciente). Provisional: la CURP aparece como repetida. ¿Se reutiliza la persona?
- **Usuarios.** ¿Hace falta restablecer contraseñas y dar de baja usuarios desde el sistema? Aún no existe.

### Citas (semana 3)
- **Cita sin cita.** Provisional: se crea ya atendida y tampoco puede encimarse con una cita agendada. ¿Debe poder encimarse? Si sí, se agrega `condition=Q(origen='agendada')` a la restricción `cita_sin_empalmes`.
- **Horario de atención.** Provisional: el calendario muestra de lunes a sábado, de 08:00 a 20:00 (`CITAS_HORA_INICIO`, `CITAS_HORA_FIN` y `CITAS_DIAS_HABILES`). Solo es visual; el servicio no restringe horarios.
- **Vigencia del link/QR del formulario.** Provisional: 24 h después del inicio de la cita (`CITAS_QR_HORAS_VIGENCIA`).
- **Cita sin registro.** Decidido (2026-11-11): nombre, apellido paterno, género y teléfono o correo; al llegar se liga o registra al paciente. La cita espontánea sigue exigiendo paciente. Provisional: el teléfono de la cita se usa como WhatsApp para el recordatorio y el link, y al registrar al paciente se propone como su WhatsApp. Los datos de la cita sin registro no se editan (si cambian, se cancela y se agenda otra). Al registrar la llegada se conservan en la cita.
- **Corregir el estado de una cita.** Provisional: una cita atendida o no atendida ya no se puede cambiar. ¿Se permiten correcciones?

### Formularios (semana 4)
- **Preguntas reales de los 2 formularios** (hombre y mujer): tipos, opciones y cuáles son obligatorias. Provisional: preguntas de ejemplo en la migración `formularios/0002`. Las reales se cargan publicando una versión nueva con otra migración de datos.
- **Corregir respuestas.** Provisional: una vez enviado, el formulario no se puede editar ni volver a llenar en esa cita. ¿Hace falta que la recepción pueda reabrirlo?

### Catálogo de estudios (semana 5)
- **Excel de estudios** (claves, nombres, categorías, precios, campos, fórmulas y ejemplos reales). Provisional: 3 estudios de ejemplo en la migración `estudios/0002` (glucosa, perfil de lípidos y espermatobioscopia básica), con claves, precios, alias y valores de referencia inventados. Los reales se cargan con otra migración de datos y sus clases en `apps/estudios/definiciones/`.
- **Quién administra qué.** Provisional: la recepción agrega y edita los alias; el químico, los valores de referencia. Ambos consultan el catálogo. ¿Los valores de referencia los captura alguien más (el admin, la recepción)?
- **Precio.** Provisional: el precio vigente solo cambia con una migración de datos (no hay pantalla). ¿Quién lo cambia y con qué frecuencia?
- **Referencia que aplica.** Provisional: si varias aplican al paciente, gana la de su género sobre la general, la de su rango de edad sobre la que no tiene edad y, al final, la más reciente. Los límites de edad se incluyen (años cumplidos).
- **Varios rangos por campo** (normal, limítrofe, alto; por ejemplo, colesterol deseable/limítrofe/alto). Provisional: un solo rango mínimo–máximo o un texto por fila.

### Pedidos (semana 6)
- **Desde qué cita se arma un pedido.** Provisional: solo desde una cita atendida (la espontánea ya nace atendida). ¿También desde una programada, antes de que llegue el paciente?
- **Estado de pago del pedido.** Provisional: pagado si todos sus estudios están pagados, pendiente si ninguno tiene pago y abonado en cualquier otro caso. Está en `apps/pedidos/estados.py`.
- **`TotalPago`.** Provisional: lo que cuesta el pedido (la suma de los precios copiados), no lo pagado. Cuando existan los abonos se podrá mostrar también lo pagado y el saldo.
- **Cuándo pasa un estudio a «en proceso».** Decidido (2026-11-03): cuando un químico lo toma de la cola (ver §3).
- **Estudio repetido en un pedido.** Provisional: no se permite el mismo estudio dos veces en un pedido.
- **Observaciones.** Decidido (2026-11-11): solo la recepción las escribe y se ven en el detalle del pedido (también los químicos). Provisional: solo se agregan; no se editan ni se borran.
- **Quitar estudios.** Provisional: se puede quitar un estudio que aún no está completado, siempre que el pedido conserve al menos uno.

### Químico (semana 7)
- **Quién captura.** Decidido (2026-11-03): solo el químico encargado. Los demás químicos y la recepción solo ven los resultados.
- **Soltar o pasar con borrador.** Decidido: solo sin captura. Provisional: un borrador sin ningún valor no cuenta como captura.
- **Cola.** Provisional: muestra solo los estudios de citas atendidas (los pedidos solo se arman de citas atendidas). Pasar a un paciente no le pide permiso al químico que lo recibe.
- **Toma por paciente.** Decidido (2026-11-11): se toma, se suelta y se pasa al paciente con todos sus estudios, y los nuevos se asignan solos a su encargado. Provisional: el paciente deja de tener encargado cuando ya no tiene estudios en proceso (por ejemplo, si todos están completados); entonces lo nuevo va a la cola. Si el encargado está dado de baja, lo nuevo también va a la cola. Con un solo estudio capturado ya no se puede soltar ni pasar al paciente.
- **Borrador.** Provisional: el químico puede guardar lo capturado sin completar; el estudio sigue en proceso. Para completarlo hacen falta todos los campos.
- **Corregir un estudio completado.** Decidido (2026-11-11): se puede hasta que se envían sus resultados; enviado ya no. Provisional: solo su químico encargado; la corrección pide todos los campos, no vuelve a borrador, y `quimico_completo` y `fecha_completado` pasan a ser los de la corrección (el historial completo llegará con la auditoría).
- **Fuera de rango.** Provisional: un valor menor al mínimo se marca como «bajo» y uno mayor al máximo como «alto», según la referencia copiada. Los textos de referencia no se marcan.
- **Qué referencia se copia.** Provisional: la vigente el día de la cita, con la edad que tenía el paciente ese día (no la del día en que se completa).

### Resultados y notificaciones (semana 8)
- **Quién envía los resultados.** Decidido (2026-10-30): solo los químicos (cualquiera, no solo el encargado), desde el pedido. La recepción ve el PDF y los envíos, pero no envía.
- **Resultados al doctor.** Decidido (2026-11-03): al enviar, el químico decide con la casilla «Enviar también al doctor», marcada por omisión. Sale solo si el pedido tiene doctor y este tiene correo o WhatsApp; si no, solo al paciente. El doctor recibe su propio mensaje con el mismo PDF.
- **Contacto del doctor.** Provisional: la migración pasó a `correo` el texto que era un correo y a `whatsapp` el que era un número de 10 a 15 dígitos (se asumió que es WhatsApp); lo demás quedó en «otros datos de contacto».
- **Paciente sin correo ni WhatsApp.** Decidido (2026-10-30): todo paciente debe tener al menos un contacto para recibir resultados (correo o WhatsApp). Se exige al registrar y al editar al paciente (el servicio lo revisa). Un paciente anterior sin contacto debe agregarlo la próxima vez que se edite; mientras tanto no se pueden enviar sus resultados.
- **Doctor sin correo ni WhatsApp.** Decidido (2026-11-03): al registrar o editar un doctor se exige al menos uno de los dos. No hay restricción en la BD: los doctores anteriores sin contacto siguen existiendo y deben agregarlo al editarse; mientras tanto los resultados solo van al paciente.
- **Reenviar.** Provisional: se puede volver a enviar un estudio ya enviado; la fecha y el usuario del primer envío no cambian.
- **WhatsApp.** Mientras no se integre la API, el envío por WhatsApp solo queda registrado en el log y cuenta como «enviado».
- **Formato del PDF y redacción de los mensajes.** Provisional: un PDF con membrete de texto (sin logo), datos de la cita, una tabla por estudio, la referencia copiada y quién lo realizó con su cédula. Está en `templates/documentos/resultados.html` y `apps/notificaciones/mensajes.py`. El correo lleva el PDF adjunto.
- **Reintentos.** Provisional: un envío fallido se reintenta a los 1, 5 y 30 minutos (`NOTIFICACIONES_REINTENTOS`); después queda «fallido» y se envía de nuevo a mano.
- **Recordatorio.** Provisional: el timer revisa cada 15 minutos y manda el recordatorio con el link del formulario cuando faltan 24 h o menos. Si la cita se reprograma, se vuelve a mandar. Generar o enviar un link nuevo invalida el anterior, también el del recordatorio.

### Cotizaciones (cambio del cliente, 2026-11-03)
- **Quién.** Decidido: solo la recepción.
- **Destino.** Decidido: un paciente registrado (sus contactos principales) o un correo/WhatsApp escrito a mano. Provisional: lo escrito reemplaza al contacto del paciente en ese canal; con paciente se usa su nombre.
- **Formato.** Provisional: PDF con membrete de texto, la lista de estudios con su categoría y precio vigente, el total en MXN y la nota «precios sujetos a cambio». Está en `templates/documentos/cotizacion.html` y el texto del mensaje en `apps/notificaciones/mensajes.py`.
- **Descuentos y vigencia.** Provisional: no hay.

## 9. Cómo cambiar una decisión

Si al implementar algo encuentras que una decisión de este documento no funciona:
1. No la cambies por tu cuenta.
2. Descríbela en el PR o avisa al equipo.
3. Cuando se acuerde, actualiza este documento en el mismo PR y agrega una línea al registro de cambios.

### Registro de cambios
- 2026-09-27: versión inicial (reglas, BD v2 + catálogos, arquitectura y plan de 10 semanas).
- 2026-10-21: semana 1 — `Persona` y `Direccion` se adelantan a la semana 1; el servicio `worker` de Docker Compose pasa a la semana 8 (su backend en BD necesita migraciones y aún no hay tareas); HSTS preload y HTTPS en nginx quedan para la semana 9, cuando haya dominio.
- 2026-10-21: semana 3 — `Citas` agrega `FechaFin` para la restricción contra empalmes (no hace falta `btree_gist`).
- 2026-10-21: semana 5 — el system check del catálogo corre solo con base de datos (`migrate` y `manage.py check --database default`), no en `runserver`; si `estudios` tiene migraciones pendientes no revisa nada, porque son las que cargan las filas nuevas.
- 2026-10-21: semana 6 — un estudio del pedido puede tener **varios químicos responsables** (decisión del equipo): `EstudiosPedido.IdQuimicoAsignado` se reemplaza por la tabla `AsignacionesQuimico`, que guarda quién asignó a cada químico y cuándo. El índice `EstudiosPedido(estado, quimico_asignado)` pasa a `EstudiosPedido(estado)` más el de la FK de la asignación. Quien completa sigue siendo uno (`IdQuimicoCompleto`).
- 2026-10-30: semana 8 — Django 6.1 trae la API `django.tasks` pero no un backend en BD: se usa `django-tasks-db` (`manage.py db_worker`). Los recordatorios los encola el servicio `recordatorios` de Docker Compose (un timer que corre `enviar_recordatorios` cada 15 minutos). El link de los correos se arma con `SITIO_URL` (obligatorio en producción). Decidido con el cliente: solo los químicos envían resultados y todo paciente debe tener al menos un correo o WhatsApp.
- 2026-11-03: cambio del cliente tras la demo — **cola de químicos**: la recepción ya no asigna químicos; los químicos toman los estudios pendientes desde la «Cola de pedidos» y cada estudio tiene **un solo encargado**. La tabla `AsignacionesQuimico` se reemplaza por `EstudiosPedido.IdQuimicoEncargado` + `FechaToma` (una migración de datos conserva al primer químico asignado de cada estudio). El encargado puede soltar el estudio o pasarlo a otro químico mientras no haya capturado nada.
- 2026-11-03: cambio del cliente — **cotizaciones**: app `cotizaciones` sin modelos; la recepción arma un paquete temporal de estudios, descarga el PDF o lo envía por correo y WhatsApp a un paciente o a un contacto escrito a mano. Decidido: el envío es directo y no queda en `Notificaciones` (excepción a §3).
- 2026-11-03: cambio del cliente — **doctores para químicos y envío al doctor**: los químicos ven, registran y editan doctores. `Doctores.Contacto` se separa en `Correo` y `WhatsApp` (más «otros datos»), con migración de datos. `Notificaciones` agrega `DestinoTipo` (paciente/doctor) y los resultados pueden ir también al doctor del pedido.
- 2026-11-03: **contacto obligatorio** — al registrar o editar un paciente o un doctor se exige un correo o un WhatsApp (en el servicio, sin restricción en la BD para no romper registros anteriores). En el doctor era opcional; lo pidió el cliente.
- 2026-11-11: cambio del cliente — **calendario para químicos**: los químicos ven el calendario de citas en solo lectura, para preparar lo necesario. Solo la recepción agenda, reprograma o marca citas; el químico no abre el detalle de la cita.
- 2026-11-11: cambio del cliente — **observaciones del pedido**: tabla `ObservacionesPedido` con notas libres (p. ej. si el paciente quiere los resultados juntos o conforme salgan). Las escribe la recepción y se ven en el detalle del pedido.
- 2026-11-11: cambio del cliente — **estudios libres en la cotización**: además de los del catálogo, la recepción escribe estudios que no tiene guardados (nombre, precio y categoría opcional). Siguen sin guardarse en la BD.
- 2026-11-11: cambio del cliente — **toma por paciente**: los químicos ya no toman estudio por estudio; toman, sueltan y pasan al paciente con todos sus estudios pendientes de todos sus pedidos. Los estudios nuevos de un paciente con encargado se le asignan automáticamente. La BD no cambia: el encargado sigue guardándose en cada estudio.
- 2026-11-11: cambio del cliente — **corregir hasta enviar**: un estudio completado ya se puede corregir; deja de poder cambiarse cuando se envían sus resultados (antes no se podía corregir nada después de completarlo).
- 2026-11-11: cambio del cliente — **citas sin registro**: `Citas.IdPaciente` pasa a ser opcional y la cita guarda nombre, apellido paterno, género, teléfono y correo de quien agenda sin estar registrado. El paciente se registra (o se elige) al llegar, y entonces la cita queda atendida. Antes había que registrar al paciente para agendar.
