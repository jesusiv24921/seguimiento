# Personal · Finanzas

Página `/personal`, integrada en el menú de la aplicación Dash existente. Reutiliza
Bootstrap, tarjetas, estilos y Plotly del proyecto. No agrega dependencias.

## Ejecutar y probar

Desde la raíz del repositorio, con Python y las dependencias instaladas:

```powershell
python -m pip install -r requirements.txt
python app/app.py
python -m unittest discover -s tests -v
```

Abrir `http://127.0.0.1:8060/personal`. La fecha inicial corresponde a Colombia.
Los tests usan archivos temporales; no modifican los datos personales.

## Persistencia y estructura

`personal.xlsx` se crea con el primer guardado, en el mismo directorio que
`seguimiento.xlsx`, respetando `SEGUIMIENTO_EXCEL_PATH`. No está versionado en Git.
Es un libro separado para que las escrituras de actividades y conocimiento no
sobrescriban las finanzas. Todas las filas tienen un `id` estable.

| Hoja | Contenido |
| --- | --- |
| categorias | id, nombre, tipo (Ingreso/Gasto), estado (Activa/Inactiva), padre opcional |
| ingresos | fecha, descripción, categoría por id, importes planeado/real, estado y observaciones |
| gastos | mismos campos, más tipo Fijo/Variable/Deuda |
| deudas | entidad, saldo inicial y actual, tasa E.A., cuotas, fecha de apertura del registro, pago programado y estado |
| movimientos | deuda por id, fecha, tipo, importe, capital y observaciones |
| proyecciones | mes, disponible proyectado, abono extraordinario y observaciones |

El guardado valida toda la operación antes de reemplazar atómicamente el archivo.
La revisión del contenido evita sobreescribir cambios realizados desde otra pestaña.
El bloqueo de escritura funciona dentro de un proceso: mantener un único worker,
como en el `Procfile` existente; no compartir el archivo con otros procesos escritores.

## Categorías y subcategorías

En **Registros → Categorías**, usar Nuevo registro para crear una categoría y
seleccionar su tipo. No existen nombres de categorías precargados ni constantes
financieras en el frontend. La categoría principal opcional permite crear jerarquías
del mismo tipo; se rechazan ciclos y nombres duplicados bajo un mismo padre y tipo.

Seleccionar el círculo de una fila para editar su nombre, tipo, padre o estado.
Renombrar actualiza el nombre mostrado en el histórico, sin modificar las filas
de ingresos/gastos, sus importes, fechas ni asociaciones. El tipo no puede cambiar
si contradice registros o subcategorías existentes.

Para desactivar, cambiar el estado a **Inactiva** y guardar. La categoría deja de
ofrecerse en nuevos registros. Sus subcategorías también quedan no disponibles
mientras la categoría principal esté inactiva. Los registros históricos siguen
visibles y pueden editarse conservando su categoría inactiva, o reasignarse a una
activa. Reactivar la categoría vuelve a habilitarla.

Eliminar solo se permite si no hay ingresos, gastos ni subcategorías asociados.
Si tiene histórico, la operación se rechaza indicando que debe desactivarse.

Los archivos de la versión anterior, con categorías como texto, se convierten en
memoria a un catálogo con identificadores deterministas por tipo y nombre. El
siguiente guardado persiste la migración junto con el cambio. Leer nunca escribe
el archivo. No se altera el archivo original si la validación falla.

## Reglas de cálculo

- Valores monetarios en pesos enteros no negativos; nulos monetarios se interpretan como cero.
- Balance = ingresos − gastos. Diferencia de ingresos y balance = real − planeado;
  diferencia de gastos = planeado − real.
- Liquidez = balance real − pagos de deuda, incluidos abonos extraordinarios.
  No repetir esos pagos como gastos. El tipo de gasto Deuda es una salida manual
  que no cambia el saldo de una obligación.
- Cuota normal/Otro: indicar explícitamente el capital amortizado. El resto del
  valor pagado no reduce capital. Interés aumenta el saldo sin salida de caja;
  no registrar otra vez un interés ya incluido en el saldo de apertura.
- Abono dirigido: todo el valor reduce capital. Pago total debe coincidir con el
  saldo a esa fecha. Se valida toda la secuencia al editar o eliminar movimientos.
- Cuotas restantes, tasa y pago programado son datos informativos editables;
  no se simula un recálculo bancario automático.
- Proyección: parte del saldo registrado a hoy y descuenta abonos de meses futuros;
  no calcula intereses ni cuotas futuras. Disponible − abono = liquidez restante.
- Histórico: conserva meses y años. Liquidez acumulada parte de cero al primer
  registro, sin asumir un saldo bancario anterior.

Para registrar el caso Davivienda, crear Compra A y Compra B desde Deudas con los
importes y cuotas correspondientes. La fecha debe ser la del saldo que se registra.
Los ejemplos no se cargan automáticamente ni se guardan como constantes.

## Render

No se ha desplegado, hecho commit ni push. No se requiere base de datos nueva ni
cambiar el comando del `Procfile`. Verificar que `SEGUIMIENTO_EXCEL_PATH` apunte al
disco persistente ya previsto por el proyecto; `personal.xlsx` se guarda a su lado.
Respaldar ambos libros. La configuración real del servicio no se ha consultado.
Mantener el login existente configurado mediante las variables de autenticación.

## Clave privada de Personal

Personal requiere una segunda clave, independiente del acceso general. Si falta
`PERSONAL_PASSWORD_HASH`, la sección permanece bloqueada incluso en local. No se
ha elegido ni configurado una clave real durante el desarrollo.

Para generar el valor de configuración, ejecutar localmente en una terminal:

```powershell
python -c "from getpass import getpass; from werkzeug.security import generate_password_hash; print(generate_password_hash(getpass('Nueva clave privada de Personal: ')))"
```

La entrada no se muestra en pantalla. Copiar el resultado completo como valor de
`PERSONAL_PASSWORD_HASH` en las variables de entorno del servicio de Render, sin
comillas adicionales. La clave puede coincidir con la del programa, aunque Personal
requiere su propio desbloqueo. No guardar la clave ni el hash en Git o en este documento.
Para local, configurar esa misma variable en el entorno del proceso antes de arrancar.

Configurar también `SEGUIMIENTO_SECRET_KEY` con un valor aleatorio privado y estable
si aún no está definido. Se puede generar con
`python -c "import secrets; print(secrets.token_hex(32))"`.
Es la clave del servidor para firmar sesiones, no la contraseña de acceso.
El login general y sus variables se conservan sin cambios.

Abrir Personal y pulsar **Desbloquear Personal**. El acceso dura 30 minutos y
puede cerrarse desde **Bloquear / gestionar acceso → Bloquear Personal**.
Otra sesión de navegador continúa bloqueada. Al cambiar el hash configurado,
las autorizaciones emitidas con el anterior dejan de ser válidas.

La verificación se aplica en el servidor a todos los callbacks de Personal,
incluyendo lectura, guardado y eliminación. El navegador no recibe los datos
financieros antes de desbloquear. Cada 30 segundos se comprueba el vencimiento
para retirar la vista; las operaciones se rechazan inmediatamente al vencer.
El login y bloqueo llevan token CSRF, hay un límite de cinco intentos cada diez
minutos por dirección remota, y las respuestas no se almacenan en caché.
El límite vive en el proceso único existente; se reinicia al reiniciar el servidor.
Las cookies usan HttpOnly y SameSite=Lax; en Render también Secure (HTTPS).

Esta separación restringe el acceso desde la aplicación. No cifra el archivo
Excel frente a administradores que tengan acceso al disco o al servicio de Render.
Conservar la clave personal en privado y bloquear al terminar en equipos compartidos.

Referencias: [seguridad de Flask](https://flask.palletsprojects.com/en/stable/web-security/)
y [configuración de sesiones](https://flask.palletsprojects.com/en/stable/config/).

## Archivos del módulo

Creados: `app/personal.py`, `app/pages/personal.py`, `tests/test_personal.py`,
`app/personal_auth.py`, `tests/test_personal_auth.py`, `PERSONAL.md`.
Modificados: `app/app.py` (menú y registro del acceso privado), `app/assets/style.css` (diseño
adaptable de Personal), `.gitignore` (libro personal y archivos temporales).
