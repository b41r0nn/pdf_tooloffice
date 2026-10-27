# Diseño — Dividir en bloques de N páginas y grupos personalizados

**Fecha:** 27 de octubre de 2026
**Estado:** propuesta, pendiente de aprobación
**Afecta a:** pestaña *Dividir* de PDF ToolOffice

---

## 1. Por qué

La impresora de la oficina sabe escanear una tanda continua y cortarla en un archivo
por documento, pero esa separación automática deja de funcionar cuando las hojas van a
doble cara. Con 50 documentos a doble cara, hoy toca escanearlos uno por uno: 50
pasadas delante de la máquina en vez de una.

La idea es invertir el orden. Escanear los 50 de corrido, en una sola pasada, y obtener
un PDF de 100 páginas. Después subirlo aquí y decir **"córtame esto cada 2 páginas"**
para recuperar los 50 archivos. El trabajo de separar pasa del escáner a la aplicación,
que puede hacerlo sin que nadie esté de pie frente a la impresora.

Las tandas no siempre son parejas: algunos documentos traen 3 páginas y otros 2. Por eso
hace falta además una **vista donde se vean las páginas** y se pueda corregir dónde
termina cada documento.

> Este documento recoge lo que el usuario pidió. El *cómo* lo elegí yo, y cada decisión
> aparece marcada como tal con su razón, para que se pueda discutir o revertir.

---

## 2. Objetivos

1. **Dividir cada N páginas.** Un documento de 10 páginas con N=2 entrega 5 archivos de
   2 páginas. N lo escribe el usuario (2, 3, 4…).
2. **Grupos personalizados.** Poder decir "estas páginas van en un archivo, estas otras
   en otro", con una vista que muestre las páginas para no tener que adivinar.
3. Que la vista personalizada **arranque del resultado de "cada N"**, porque el caso real
   es "casi todos van de a 2, menos unos pocos".
4. No romper nada de lo que la pestaña *Dividir* ya hace.

## 3. Lo que queda fuera (no-objetivos)

- **Detectar solos dónde termina cada documento** (páginas en blanco, códigos de barras,
  hojas separadoras, OCR). Es otro problema, mucho más grande, y conviene decidirlo
  después de ver cómo funciona el corte manual.
- **Grupos con páginas sueltas no seguidas** (ej.: las páginas 1, 5 y 9 en un mismo
  archivo). Cada grupo es un tramo seguido. En una tanda escaneada los documentos
  siempre van seguidos, y para sacar páginas sueltas ya está el modo *Un rango*.
- **PDF protegidos con contraseña.** La pestaña *Dividir* ya los rechaza hoy; esto no lo
  cambia. Si hace falta, es un trabajo aparte (ver §10).
- **Renombrar cada archivo de salida uno por uno** dentro de la aplicación.

## 4. Qué sería un fracaso

- Que separar 50 documentos requiera 50 acciones del usuario. Si no se gana tiempo
  frente a escanear uno por uno, la funcionalidad no sirve.
- Que la vista se congele al abrir un escaneo de 100 páginas.
- Que el usuario no pueda saber, antes de descargar, cuántos archivos le van a salir.

---

## 5. Cómo lo resuelven otras herramientas

| Herramienta | Modos que ofrece |
|---|---|
| BentoPDF | *Range* (texto `1-3, 5, 8-10`), *Visual Select* (clic en miniaturas), *Even/Odd*, *All Pages*, *Bookmarks*, ***Every N Pages*** |
| iLovePDF | *Split by range* con **rangos fijos** y **rangos personalizados**: un campo por rango y un botón "Add Range" |
| Stirling PDF | *Split by Sections* con ajustes predefinidos y un modo personalizado con números de página separados por comas |
| Square-9 GlobalCapture | Separación por **número fijo de páginas** (ej.: cada 3), o por hoja separadora |

**Lo que aprendí de ahí:**

- "Cada N páginas" es un modo estándar y se llama así en todas partes. No hay que
  inventar nombre.
- Para lo personalizado hay dos escuelas: **escribir los rangos** (texto) o **marcarlos
  viendo las páginas** (miniaturas). Ninguna de las dos sobra.
- Ninguna de estas herramientas está pensada para el caso concreto de "una tanda
  escaneada donde casi todos los documentos miden lo mismo". Ahí es donde esta
  aplicación puede quedar mejor que las demás: **partiendo de "cada 2" y corrigiendo las
  excepciones**, en vez de obligar a describir los 50 grupos desde cero.

---

## 6. Decisión central: el texto manda, la vista lo escribe

**Decisión mía.** El servidor recibe los grupos como un texto corto: `1-2,3-5,6-7`. La
vista con miniaturas no es un canal aparte: es un editor que escribe ese mismo texto en
un campo visible.

Por qué así:

- El servidor termina con **un solo contrato**, fácil de validar, de registrar en el log
  y de probar sin navegador.
- Quien ya sabe lo que quiere puede **escribirlo directamente** y saltarse la vista.
- Si la vista falla (navegador viejo, PDF enorme, equipo lento), **la función sigue
  sirviendo**. No se pierde la herramienta por un problema de dibujo.
- El trabajo del servidor y el de la vista quedan **independientes**: se pueden construir
  y probar por separado.

**Qué cuesta si me equivoco:** si más adelante hacen falta grupos con páginas sueltas, el
texto se queda corto y habría que ampliar la sintaxis (§10).

### Sintaxis

```
1-2,3-5,6-7,9-10
```

- La **coma separa archivos**. Cada trozo es un archivo de salida.
- Cada trozo es un tramo seguido: `3-5`, o una sola página: `6`.
- El orden de los trozos es el orden de los archivos de salida.

**Reglas de validación** (decisiones mías, cada una con su motivo):

| Regla | Qué pasa | Por qué |
|---|---|---|
| Página fuera de 1..total | Error con mensaje claro | Error de dedo |
| `5-3` (inicio mayor que fin) | Error | Error de dedo |
| **Se pueden dejar páginas fuera** | Permitido | Útil de verdad: al escanear a doble cara un documento de 3 páginas sale con una 4.ª cara en blanco, y hay que poder descartarla |
| **Dos grupos que comparten una página** | Error, diciendo qué página | En una lista de 50 grupos, un solapamiento casi siempre es un error de dedo. Ojo: esto impide a propósito repetir una página en dos archivos |
| **Los grupos pueden ir en cualquier orden** | Permitido: `6-7,1-2` entrega primero las páginas 6-7 | El orden de los trozos es el orden de los archivos, así que el texto sirve además para reordenar. El solapamiento se busca por conjunto de páginas, no comparando vecinos |
| Máximo 500 archivos de salida | Error | Evita un ZIP desbocado y deja dar un mensaje amable en vez de quedarse sin memoria |
| Texto vacío | Error | — |

**Estricto a propósito.** El modo *Un rango* que ya existe recorta en silencio (`fin = min(fin, total)`).
Los modos nuevos no: avisan. Son dos situaciones distintas — en *Un rango* el usuario
escribe dos números y ve lo que pasa; aquí puede haber 50 grupos y un número mal puesto
tiene que saltar a la vista, no colarse.

---

## 7. Lo que verá el usuario

La pestaña *Dividir* gana dos opciones junto a las cuatro de hoy:

```
Elige qué páginas sacar
(•) Un rango            ( ) Cada página por separado (ZIP)
( ) Solo las pares      ( ) Solo las impares
( ) Cada N páginas      ( ) Grupos personalizados
```

**Decisión mía: la opción marcada por defecto sigue siendo *Un rango*,** como hoy. Quien
ya usa la pestaña para sacar un rango la encuentra donde espera. Es un atributo de una
línea: si resulta que *Cada N páginas* va a ser lo más usado, se cambia en un minuto.

### 7.1 Cada N páginas

```
┌──────────────────────────────────────────────────────┐
│  Páginas por archivo                                  │
│  ┌────┐                                               │
│  │ 2  │   De un PDF de 100 páginas salen 50 archivos. │
│  └────┘                                               │
│                                                        │
│  Ideal para tandas escaneadas: si cada documento       │
│  ocupa 2 hojas, pon 2.                                 │
└──────────────────────────────────────────────────────┘
```

- Un solo campo numérico. Valor por defecto **2** (el caso de doble cara).
- Debajo, el cálculo en vivo: *"De un PDF de 100 páginas salen 50 archivos."* El número
  de páginas ya lo trae `/api/paginas`, que hoy se llama al subir el archivo.
- Si la división no es exacta, lo dice: *"El último archivo tendrá 1 página."*
- Si N es mayor o igual que el total, sale **un solo archivo con todo**. No es un error:
  es lo que pediste, y avisar de ello sería ruido.
- Si salieran más de 500 archivos (N=1 en un PDF de 600 páginas), da error y manda a la
  opción que ya existe: *"Son más de 500 archivos. Usa «Cada página por separado»."* El
  aviso sale del cálculo en vivo, **antes** de subir nada.

### 7.2 Grupos personalizados

```
┌──────────────────────────────────────────────────────────────┐
│  Grupos: 1-2,3-5,6-7                            [ Ver páginas ]│
│                                                                │
│  50 documentos · 100 páginas                                   │
│  Reagrupar cada [ 2 ] páginas                                  │
│  ┌──────────────────────────────────────────────────────────┐ │
│  │ Documento 1 · 2 páginas          [ Unir con el siguiente ]│ │
│  │  ┌───────┐ ✂ ┌───────┐                                    │ │
│  │  │  pág  │   │  pág  │                                    │ │
│  │  │   1   │   │   2   │                                    │ │
│  │  └───────┘   └───────┘                                    │ │
│  └──────────────────────────────────────────────────────────┘ │
│  ┌──────────────────────────────────────────────────────────┐ │
│  │ Documento 2 · 3 páginas          [ Unir con el siguiente ]│ │
│  │  ┌───────┐ ✂ ┌───────┐ ✂ ┌───────┐                        │ │
│  │  │   3   │   │   4   │   │   5   │                        │ │
│  │  └───────┘   └───────┘   └───────┘                        │ │
│  └──────────────────────────────────────────────────────────┘ │
└──────────────────────────────────────────────────────────────┘
```

**Decisión mía: un recuadro por archivo de salida, no una cuadrícula plana de páginas.**
Lo que el usuario está revisando es *qué páginas van juntas*, y con recuadros eso se ve
de un golpe. En una cuadrícula plana con etiquetas de color habría que ir leyendo etiqueta
por etiqueta. **Si me equivoco**, es un cambio de CSS y de cómo se agrupan los nodos, no
del contrato ni del servidor.

Cómo se maneja. **Tres acciones, no dos:**

- **Cortar:** el botón `✂` entre dos páginas de un mismo grupo lo parte en dos.
- **Unir:** el botón `Unir con el siguiente` de la cabecera junta ese grupo con el de abajo.
- **Descartar una página:** cada miniatura tiene un botón para dejarla fuera. La página
  se queda a la vista, apagada y tachada, y deja de contar para los archivos de salida.
  Se puede volver a meter pulsando otra vez.
- **Reagrupar cada N:** vuelve a empezar con grupos parejos de N páginas. Es el botón que
  une las dos opciones: pones 2, ves el resultado y corriges los que llevaban 3.

**Por qué hace falta descartar.** Es el caso que motiva todo esto: un documento de 3
páginas escaneado a doble cara llega como 4 caras, con la última en blanco. Sin descartar,
esa cara en blanco se convertiría en un archivo suelto. Con las dos acciones —unir las
cuatro y descartar la última— sale el documento de 3 páginas que se quería. §6 ya permite
dejar páginas fuera; sin este botón, eso solo se podría hacer escribiendo el texto a mano.

Si se descarta una página del medio de un grupo, el grupo se parte en dos documentos: la
sintaxis solo admite tramos seguidos (§6). **No es un efecto escondido**: la vista se
redibuja y se ven los dos recuadros al instante. El caso real descarta siempre en el
borde, nunca en el medio.

Más detalles:

- Cada acción **reescribe el campo de texto** de arriba. El texto y la vista siempre
  dicen lo mismo.
- **Mientras la vista está abierta, el campo de texto es de solo lectura** y refleja lo
  que la vista dice. Al cerrarla vuelve a ser editable. **Decisión mía:** así se evita un
  analizador en vivo sobre texto a medio escribir, que es mucho más código y más formas
  de romperse. Las dos maneras de trabajar —escribir o dibujar— no compiten.
- Al **abrir** la vista se lee una vez lo que haya en el campo y se dibujan esos grupos.
  Si el texto no es válido, la vista no se abre y se señala el error en el campo.
- Todos los controles son `<button>` de verdad, con `aria-label` que nombra la página
  (*"Cortar después de la página 7"*, *"Descartar la página 8"*), para que funcionen con
  teclado y lector de pantalla, igual que el resto de la aplicación.

### 7.3 De dónde salen las miniaturas

**Decisión mía: se dibujan en el navegador con la PDF.js que la aplicación ya trae**
(`app/static/pdfjs/build/pdf.mjs`, v6.4.299, verificado: exporta `getDocument` y
`GlobalWorkerOptions`).

Alternativa descartada: generarlas en el servidor con PyMuPDF y una sesión temporal,
como hace la pestaña *Editar*.

| | En el navegador | En el servidor |
|---|---|---|
| Dependencias nuevas | ninguna | ninguna |
| Estado en el servidor | **ninguno** | sesión, carpeta temporal, limpieza |
| Memoria del servidor | **nada** | dibujar 100 páginas, con `mem_limit` de 1,5 GB y 2 workers |
| Subidas | **una sola, al dividir** | una extra para abrir la sesión |
| Velocidad al ajustar | **inmediata** | una petición por miniatura |
| Trabajo del equipo del usuario | dibujar 100 miniaturas | nada |

El servidor tiene 3,7 GB compartidos con los demás contenedores; los equipos de la
oficina están sobrados para dibujar miniaturas pequeñas. Y lo importante: la pestaña
*Dividir* **sigue sin guardar estado**, como hoy. Añadir sesiones a una herramienta que
no las necesita es complejidad que después hay que limpiar.

Detalles que el constructor debe respetar:

- `import()` dinámico desde `main.js` (que es un script normal, no un módulo).
- Las rutas de `pdf.mjs` y `pdf.worker.mjs` **no se pueden escribir a mano** en el JS:
  tienen que llegar desde la plantilla en un `data-…`, para que lleven el `?v=` de caché.
  Ya hay precedente: `data-css` en el `<iframe>` del editor.
- Dibujar **solo lo que se ve**, con `IntersectionObserver`. Con 100 páginas, dibujar
  todo de golpe congela la pestaña.
- Escala pequeña (miniaturas de ~120 px de ancho).
- Si el PDF está protegido, PDF.js lanza `PasswordException`: mostrar el mismo mensaje
  que ya da el servidor y dejar el campo de texto disponible.

---

## 8. Contrato del servidor

Se amplía `/api/division`, que ya existe. **No se crean endpoints nuevos**: la
herramienta ya reparte por `modo` y así sigue la misma forma.

### Modo `cada`

| Campo | Valor |
|---|---|
| `archivo` | el PDF |
| `modo` | `cada` |
| `paginas_por_archivo` | entero ≥ 1 |

Respuesta: **ZIP**, `{base}_dividido.zip`.

### Modo `personalizado`

| Campo | Valor |
|---|---|
| `archivo` | el PDF |
| `modo` | `personalizado` |
| `grupos` | `1-2,3-5,6-7` |

Respuesta: **ZIP**, `{base}_dividido.zip`.

### Nombres dentro del ZIP

`{base}_01.pdf`, `{base}_02.pdf`, … con los ceros necesarios según cuántos sean.

**Decisión mía:** nombres cortos, sin el rango de páginas dentro. El usuario va a
renombrar cada archivo con el número de factura, y un nombre corto se renombra más
fácil. **Si me equivoco**, es cambiar una línea del formato.

### Siempre ZIP

**Decisión mía:** aunque salga un solo archivo, se entrega ZIP. Un modo que a veces
devuelve PDF y a veces ZIP obliga a mirar el tipo en el front y complica el código para
un caso raro. El modo *Un rango* sigue devolviendo un PDF suelto, que es lo suyo.

### Registro

El campo `detalle` del log guarda `modo=cada; paginas_por_archivo=2; archivos=50` o
`modo=personalizado; grupos=50; paginas=100`. **El texto de los grupos no se guarda
entero**: con 500 grupos son miles de caracteres en la base de datos.

---

## 9. Trabajo a realizar

Cuatro bloques. El 1 y el 2 no dependen de la vista; el 3 es la vista.

| # | Bloque | Toca | Depende de |
|---|---|---|---|
| 1 | **Servidor:** `dividir_en_bloques` y `dividir_por_grupos` en `services.py`, con el analizador de la sintaxis y sus validaciones; los dos modos nuevos en `routes.py`. Pruebas de cada regla del §6. | `app/services.py`, `app/routes.py`, `tests/test_routes.py` | — |
| 2 | **Formulario:** las dos opciones nuevas, el campo numérico con el cálculo en vivo, el campo de texto de grupos y el botón **Rellenar cada [N] páginas** que lo llena solo. Más el analizador de la sintaxis en JS, que da el contador *"→ 50 archivos"*. Sin miniaturas, ya es usable de verdad. | `app/templates/index.html`, `app/static/js/main.js`, `app/static/css/style.css` | 1 |
| 3 | **Vista de páginas:** carga de PDF.js, miniaturas perezosas, recuadros por documento, cortar / unir / descartar / reagrupar, escritura del campo de texto. Reutiliza el analizador del bloque 2. | `app/static/js/` (archivo nuevo), `index.html`, `style.css` | 2 |
| 4 | **Cierre:** versión 2.4.0, changelog del README, texto de ayuda de la pestaña, repaso de que no haya desbordes de 320 a 1440 px. | `README.md`, `app/__init__.py` | 1-3 |

### Restricciones que atraviesan todo

- **Sin dependencias nuevas.** PyMuPDF y PDF.js ya están; `zipfile` es de la biblioteca
  estándar. La aplicación se apoya solo en herramientas libres y eso no cambia.
- **Mensajes de error en español, dirigidos a quien usa la herramienta**, como el resto.
  `ValueError` para lo que es culpa del usuario (sale como 400 con el mensaje visible);
  cualquier otra cosa es 500 con mensaje genérico. Así funciona ya `error_response`.
- **Español en el código** (nombres de función, variables, comentarios), como el resto del
  proyecto.
- **Accesibilidad:** controles que son `<button>`, `aria-label` que nombra la página,
  foco visible. La aplicación ya cumple AA y no se baja de ahí.
- **Responsivo de 320 a 1440 px**, verificado en la versión 2.3.1 y que debe seguir así.
- El límite de **50 MB por archivo no se toca** en este trabajo (ver §10).

---

## 10. Riesgos y lo que queda abierto

| Riesgo | Detalle | Qué propongo |
|---|---|---|
| **El escaneo no cabe en 50 MB** | 100 páginas escaneadas a 300 ppp pueden rondar 20-40 MB, pero un escaneo a color o a más resolución se pasa. El límite actual es 50 MB (`MAX_CONTENT_LENGTH`). | No cambiarlo ahora. **Probar con una tanda real de 50 documentos** antes de decidir. Subirlo afecta a la memoria del servidor (1,5 GB, 2 workers) y es una decisión aparte. Mientras tanto, la pestaña *Comprimir* es la salida. |
| **PDF protegidos** | *Dividir* ya los rechaza hoy. La vista dará el mismo error. | Dejarlo fuera. Si hace falta, añadir el campo de contraseña a la pestaña entera es un trabajo propio. |
| **El ZIP se arma en memoria** | El modo *Cada página por separado* ya lo hace así. Con un PDF de 50 MB, el ZIP ocupa otro tanto. | No es nuevo, pero conviene medirlo con el archivo real en la prueba de arriba. |
| **Navegador antiguo** | Las miniaturas necesitan módulos en el *worker* (Chrome/Edge 80+, Firefox 114+). | La aplicación ya usa `:has()` y `@property`, que piden navegadores igual de nuevos. El campo de texto queda como salida si acaso. |
| **El proyecto no está en git** | `pdf_tooloffice` no es un repositorio; se despliega por tar. Eso deja sin red de seguridad la ejecución por tareas (sin ramas, sin diffs, sin volver atrás). | **Correr `git init` antes de empezar.** Es la decisión que más conviene resolver antes de escribir código. |

### Preguntas abiertas que no bloquean

- ¿Hace falta algún día detectar solos los cortes (hoja en blanco, código de barras)?
  Mejor decidirlo después de usar el corte manual un par de semanas.
- ¿Querrán nombrar los archivos desde la vista en vez de renombrarlos después?

---

## 11. Decisiones que tomé yo, en una lista

Para repasarlas de un vistazo y echar atrás la que no guste:

1. **El texto `1-2,3-5` es el contrato; la vista solo lo escribe.** Mantiene el servidor
   simple y la función viva aunque la vista falle.
2. **La coma separa archivos; cada grupo es un tramo seguido.** Sin páginas sueltas.
3. **Se pueden dejar páginas fuera; los solapamientos dan error.** Lo primero sirve para
   las caras en blanco; lo segundo caza errores de dedo en listas largas.
4. **Máximo 500 grupos.**
5. **Un recuadro por archivo de salida**, en vez de una cuadrícula plana con etiquetas.
6. **Miniaturas en el navegador**, no en el servidor. La pestaña sigue sin estado.
7. **Siempre ZIP** en los dos modos nuevos, aunque salga un solo archivo.
8. **Nombres cortos** dentro del ZIP: `{base}_01.pdf`.
9. **Se amplía `/api/division`**, no se crean endpoints nuevos.
10. **El log no guarda el texto completo de los grupos**, solo cuántos son.
11. **El límite de 50 MB no se toca** en este trabajo.
12. **Este documento va en la raíz del proyecto**, junto a `README.md` y
    `AUDITORIA_2026-10.md`, siguiendo la costumbre del repositorio.

Y estas salieron de la revisión del documento (§13):

13. **La vista lleva un botón para descartar páginas**, no solo cortar y unir. Sin él, el
    caso que motiva todo esto —la cara en blanco del escaneo a doble cara— solo se podría
    arreglar escribiendo el texto a mano.
14. **Mientras la vista está abierta, el campo de texto es de solo lectura.** Se lee una
    vez al abrir. Nada de analizar texto a medio escribir.
15. **El botón «Rellenar cada N páginas» va en el formulario**, no solo dentro de la
    vista. Así el modo personalizado sirve desde el primer bloque de trabajo, sin obligar
    a escribir 50 grupos a mano.
16. **Hay un analizador de la sintaxis en JS**, compartido por el contador y la vista. El
    servidor sigue siendo la autoridad: el navegador solo adelanta la cuenta de archivos.
17. **Los grupos pueden ir en cualquier orden** y el solapamiento se detecta por conjunto
    de páginas. El texto sirve además para reordenar.
18. **La opción marcada por defecto sigue siendo *Un rango*.**

---

## 12. Lo que falta por saber

**Una tanda real escaneada.** Para cerrar el riesgo del límite de 50 MB y el del ZIP en
memoria (§10) hace falta un PDF de verdad: los 50 documentos a doble cara escaneados de
corrido, tal como salen de la impresora. Sin ese archivo, la comprobación final se queda
en "se ve bien y no se desborda", y las dos dudas siguen abiertas después de entregar.

Con el archivo, el bloque 4 gana un paso medido: tamaño del PDF, memoria del contenedor
al dividirlo y tiempo hasta el ZIP, con un umbral de aprobado escrito antes de medir.

---

## 13. Revisión del documento

Antes de darlo por bueno lo leyó un revisor que no estuvo en la conversación, con el
encargo de decir qué le faltaba para poder planificar sin adivinar. Sacó ocho huecos.
Siete están resueltos arriba (decisiones 13 a 18, más el tope de 500 archivos en el modo
`cada` y qué pasa si N supera el total, en §7.1). El octavo es la tanda real escaneada
de §12, que solo puede aportar quien usa la impresora.
