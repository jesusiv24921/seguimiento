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
| gastos_diarios | id, fecha, descripción, categoría por id, valor pagado y observaciones |
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

En **Registros → Gastos diarios**, registrar cada pago con fecha, descripción,
categoría y valor (por ejemplo Taxi, 20000). La fecha predeterminada es hoy para
el mes actual; para otros meses empieza en el día 1. Cada pago puede editarse o
eliminarse seleccionando su fila. El resumen agrupa los pagos por fecha y categoría.
Dos pagos iguales son válidos y se conservan como movimientos separados.

El real de gastos suma los pagos diarios y los valores reales manuales anteriores.
El planeado proviene de **Presupuesto y gastos previos**. No copiar el presupuesto
al campo real ni volver a incluir allí pagos ya registrados en el diario. Si un
real manual representa solo un presupuesto, corregirlo a cero antes de registrar
los pagos diarios correspondientes. No se alteran automáticamente valores previos.
Los libros existentes se leen sin modificar; la hoja nueva se crea al guardar.

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

No se requiere base de datos nueva ni cambiar el comando del `Procfile`.
`SEGUIMIENTO_EXCEL_PATH` apunta al disco persistente; `personal.xlsx` se guarda
a su lado. Respaldar ambos libros.
Mantener el login existente configurado mediante las variables de autenticación.

## Acceso a Personal

Personal utiliza el login general del programa sin pedir una segunda clave.
Quien tenga acceso al programa puede entrar a Personal.
`PERSONAL_PASSWORD_HASH` ya no se utiliza. Los enlaces antiguos de acceso y
bloqueo redirigen a `/personal`. Se conserva el control de origen de escrituras
y las respuestas no se almacenan en cache.

## Archivos del módulo

Creados: `app/personal.py`, `app/pages/personal.py`, `tests/test_personal.py`,
`app/personal_auth.py`, `tests/test_personal_auth.py`, `PERSONAL.md`.
Modificados: `app/app.py` (menú y registro del acceso privado), `app/assets/style.css` (diseño
adaptable de Personal), `.gitignore` (libro personal y archivos temporales).
