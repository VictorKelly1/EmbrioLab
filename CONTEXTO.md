# CONTEXTO — EmbrioLab (Fase 1)

> Documento de referencia para desarrolladores y agentes de IA que trabajen en este repositorio.
> **Léelo completo antes de escribir código.** Contiene las decisiones de negocio, el diseño de la base de datos, la arquitectura y el plan de trabajo de 10 semanas.
> Si algo de aquí contradice al código, manda este documento: consulta antes de cambiar una decisión (ver §9).

Última actualización: 2026-09-27

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
| **Recepcionista** | Agenda citas desde un calendario. Registra, edita, busca y da de baja lógica a pacientes. Marca la cita como atendida o no atendida y envía el QR del formulario. Arma los **pedidos** (relaciona el nombre que dio el doctor con el catálogo de estudios, usando alias) y **asigna un químico** a cada estudio. Registra el estado de pago. |
| **Químico** | Ve **todos** los pedidos, actuales e históricos, **con filtros** (por químico asignado, estado, paciente, fecha…). Captura resultados; el sistema hace los cálculos internos. Completa estudios y envía los resultados, uno por uno o en conjunto. Consulta al paciente y el catálogo. |
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
- **No puede haber dos citas empalmadas** (hay un solo horario de atención). Valídalo en el servicio **y** en la BD, por ejemplo con un `ExclusionConstraint` (btree_gist) sobre el rango `[fecha_hora, fecha_hora + 30 min)`, para que sea seguro aunque haya concurrencia.
- **Estados:** `programada`, `atendida`, `no_atendida`. Reprogramar = cambiar `fecha_hora`.
- **Las canceladas se BORRAN** (no se guardan).
- Se puede atender a alguien **sin cita**: se crea una cita con `origen = espontanea`.
- El recordatorio sale **24 h antes** y queda marcado con `recordatorio_enviado`.

### Folio
- Se forma con las **2 primeras letras del apellido paterno + 2 del materno + el número de paciente**.
- Es el mismo en **todas las citas del mismo paciente** (así lo maneja el cliente) y el paciente lo ve.
- Pendiente: la regla para quien no tiene apellido materno. **La decide el cliente.** Mientras tanto, déjala aislada en una sola función.

### Pacientes
- Se registran **una sola vez**, con sus datos fijos.
- **CURP obligatoria y única.** INE opcional. Género: `masculino` / `femenino`.
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
  - La lista de trabajo del químico son los estudios `en_proceso`.
- Un pedido está **completado** cuando todos sus estudios están completados **y** enviados, estén pagados o no.
- `Pedido.estado`, `Pedido.estado_pago` y `Pedido.total_pago` son **derivados**. Se guardan en la tabla, pero **solo los actualiza un servicio** (ver §6).
- Se registra **quién asignó, quién completó y quién envió** cada estudio.
- No hay validador aparte: el químico es el responsable.

### Pagos
- El pago es **por estudio**, con 3 estados: `pagado`, `abonado`, `pendiente`.
- **El envío de resultados NO depende del pago.**
- Los abonos con monto son de una fase posterior. Por ahora solo se guarda el estado, pero **`estado_pago` se cambia exclusivamente desde un servicio**, para poder conectar después la tabla `Abonos`.

### Almacenamiento de formularios y resultados
- Solo se guarda **JSON**. **No se almacenan PDFs:** el PDF se genera al vuelo.

### Estudios
- Son **~30 estudios fijos, definidos en código**, porque tienen cálculos internos. El cliente entrega un Excel con sus campos, operaciones y claves.
- No hay paquetes de estudios.
- La recepcionista guarda **alias**: el nombre que usa el doctor → el estudio del catálogo.

### Valores de referencia
- El cliente los cambia seguido, a veces se los proporcionan terceros y varían por estudio. Por eso van **en la BD** y no en código. La tabla es **provisional**.
- Al completar un estudio, la referencia que se usó **se copia dentro del JSON de resultados**.

### Notificaciones
- Se envían por **correo y WhatsApp**. La API de WhatsApp se integra después: deja la abstracción lista.
- Todo envío queda registrado en la tabla `Notificaciones`.

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
| **Doctores** | Id, Nombre, Contacto |
| **Donadores** | ⏸ PENDIENTE (falta información del cliente). Es un tipo especial de paciente con un inventario de muestras de esperma: código, fecha, disponible/usada y doctor al que se envió. **No implementar.** |

### Citas y formularios
| Tabla | Campos |
|---|---|
| **Citas** | Id, IdRecepcionista, IdPaciente, FechaHora, Asunto, Estado, Origen (agendada/espontanea), NumeroFolio, TokenQR (**hash**), TokenExpiracion, RecordatorioEnviado |
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
| **EstudiosPedido** | Id, IdPedido, IdEstudio, NombreSolicitado, Precio (copia al momento del pedido), **VersionEstudio**, IdQuimicoAsignado, Estado, EstadoPago, Resultados (JSON), IdQuimicoCompleto, FechaCompletado, IdUsuarioEnvio, FechaEnvio |
| **Abonos** | ⏸ FASE POSTERIOR, no crear. Diseño previsto: Id, IdEstudioPedido, Monto, Fecha, MetodoPago, IdRecepcionista |

### Notificaciones
| Tabla | Campos |
|---|---|
| **Notificaciones** | Id, Tipo (recordatorio/qr/resultados), Canal (correo/whatsapp), Destinatario, IdCita (null), IdEstudioPedido (null), Estado (pendiente/enviado/fallido), Error, FechaEnvio |

### Índices mínimos
- `Citas(fecha_hora)`
- `EstudiosPedido(estado, quimico_asignado)`
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
  documentos/      PDF de resultados
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
| **1** | Cimientos | Settings base/dev/prod; PostgreSQL + Docker Compose; `es-mx`/TZ; ruff + pytest; `core` (modelos base, borrado lógico, `RolRequerido`); `cuentas` con el usuario personalizado y las 3 tablas de rol; login/logout; layout base + HTMX; Argon2 + axes |
| **2** | Personas y pacientes | `personas` y `pacientes` (modelos + servicios + selectores); CRUD de pacientes para la recepcionista; búsqueda por nombre (trigram) y CURP; borrado lógico; número de paciente y **función de folio**; Doctores; el admin registra usuarios con rol |
| **3** | Citas | Modelo Cita con restricción contra empalmes; calendario (vista día/semana) para agendar y ver las próximas; reprogramar; cancelar = borrar; cita espontánea; marcar atendida/no atendida; generación del token QR (hash, expiración, un solo uso) |
| **4** | Formularios | Formularios + versiones + validador del esquema; constructor de forms dinámicos; **migración de datos con los 2 formularios del cliente**; página pública del QR (rate limit, token de un uso); FormularioLlenado; la recepcionista ve las respuestas |
| **5** | Catálogo de estudios | Modelos de estudios, alias y valores de referencia; **registro de definiciones + system check**; carga del catálogo (claves, nombres, precios) desde el Excel del cliente; CRUD de alias y de valores de referencia; primeras definiciones con pruebas contra ejemplos del Excel |
| **6** | Pedidos (recepción) | Armar el pedido desde una cita; relacionar el nombre solicitado con un estudio (sugerencias por alias y guardado de alias nuevos); asignar químico; estado de pago por estudio; servicio `recalcular_pedido`; máquina de estados |
| **7** | Químico | Lista de todos los pedidos **con filtros** (asignado, estado, paciente, fecha, pago); detalle del pedido y del paciente; captura de resultados con un form generado desde la definición; cálculos; completar (con copia de la referencia); historial. Continuar con las definiciones de estudios |
| **8** | Resultados y notificaciones | PDF al vuelo (WeasyPrint); tabla Notificaciones + outbox + worker; canal de correo (SMTP) y stub de WhatsApp; envío de resultados individual o en conjunto; recordatorios de 24 h (comando programado); envío del QR |
| **9** | Cierre funcional y endurecimiento | **Terminar las ~30 definiciones de estudios**; auditoría; settings de producción + `check --deploy`; respaldos; reportes básicos del admin (según lo que entregue el cliente); pulir la interfaz; revisar consultas N+1 e índices |
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

- La **zona horaria** del laboratorio (todavía no se sabe; usar `America/Mexico_City` de forma provisional y dejarla configurable por `.env`).
- El formato del **número de pedido**.
- La regla del folio sin apellido materno (la decide el cliente).
- El diseño de Donadores (falta información del cliente).
- Los reportes del admin (los define el cliente).

## 9. Cómo cambiar una decisión

Si al implementar algo encuentras que una decisión de este documento no funciona:
1. No la cambies por tu cuenta.
2. Descríbela en el PR o avisa al equipo.
3. Cuando se acuerde, actualiza este documento en el mismo PR y agrega una línea al registro de cambios.

### Registro de cambios
- 2026-09-27: versión inicial (reglas, BD v2 + catálogos, arquitectura y plan de 10 semanas).
