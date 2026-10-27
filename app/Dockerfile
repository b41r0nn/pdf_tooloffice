FROM python:3.12-slim

# Fuentes libres métricamente compatibles (Arial/Times/Courier -> Liberation,
# Calibri -> Carlito, Cambria -> Caladea): la edición de texto escribe con la
# misma métrica que el original. LibreOffice convierte Word/Excel a PDF con
# fidelidad; para una imagen más liviana: --build-arg INSTALAR_LIBREOFFICE=0
# Tesseract (spa/eng) da OCR a los PDF escaneados en PDF → Excel / Word.
ARG INSTALAR_LIBREOFFICE=1
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        fonts-liberation2 fonts-crosextra-carlito fonts-crosextra-caladea fonts-dejavu-core \
        tesseract-ocr-spa tesseract-ocr-eng \
    && if [ "$INSTALAR_LIBREOFFICE" = "1" ]; then \
        apt-get install -y --no-install-recommends libreoffice-writer-nogui libreoffice-calc-nogui; \
    fi \
    && rm -rf /var/lib/apt/lists/* \
    && fc-cache -f

# El usuario de la app no tiene home propio: cachés de fontconfig/LibreOffice en /tmp
ENV HOME=/tmp XDG_CACHE_HOME=/tmp/.cache PYTHONUNBUFFERED=1

WORKDIR /srv

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . ./app/

# uid 1000 = usuario sistemas del servidor: puede escribir en las carpetas montadas
RUN useradd --uid 1000 --home-dir /srv --no-create-home app \
    && mkdir -p /srv/app/uploads /srv/app/database \
    && chown -R app /srv/app/uploads /srv/app/database
USER app

EXPOSE 5000

# gunicorn toma el número de workers de WEB_CONCURRENCY (el compose de producción usa 2)
ENV WEB_CONCURRENCY=3
CMD ["gunicorn", "--bind", "0.0.0.0:5000", "--threads", "4", "--timeout", "300", "app:create_app()"]
