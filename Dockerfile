# Pohjakuva lukittu tarkkaan Python-versioon ja Debian-julkaisuun (trixie).
FROM python:3.12.14-slim-trixie

# Ei pip-välimuistia eikä pipin versiotarkistusta.
# Pyright ja Semgrep eivät tarkista uusia versioita, jolloin lokeihin ei tule
# ylimääräisiä varoituksia. Semgrep hakee säännöt verkosta ajon aikana (--config auto).
ENV PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PYRIGHT_PYTHON_IGNORE_WARNINGS=1 \
    SEMGREP_ENABLE_VERSION_CHECK=0

# Luodaan työhakemisto.
WORKDIR /workspace

# Peruskomennot: git aineistojen kloonaukseen, ca-certificates ja curl HTTPS-yhteyksiä
# varten sekä build-essential varalle, jos jokin riippuvuus joudutaan kääntämään lähdekoodista.
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    ca-certificates \
    curl \
    git \
    && rm -rf /var/lib/apt/lists/*

# Asennetaan pip ja pipx lukituilla versioilla.
# Aineistojen importtaamat kirjastot (flask, flask-caching, flask-restful, requests)
# asennetaan myös järjestelmän Pythoniin, koska Pyright ratkaisee importit
# PATH:ssa olevan Python-tulkin kautta eikä oman pipx-ympäristönsä kautta.
# Muuten puuttuvat kirjastot näkyisivät vääriä import-virheinä.
ARG DATASET_LIBS="flask==3.1.3 flask-caching==2.4.1 flask-restful==0.3.10 requests==2.34.2"
RUN python3 -m pip install pip==26.2.1 pipx==1.17.6 ${DATASET_LIBS}

ENV PATH="/root/.local/bin:${PATH}"

# Kopioidaan staattisten analysaattoreiden luettelo (versiot lukittu tiedostossa).
COPY static_analyzers.txt .

# Asennetaan analysaattorit pipx:llä, kukin omaan virtuaaliympäristöönsä.
# Rivit ovat muotoa paketti==versio. pipx inject vaatii pelkän paketin nimen,
# joten versio poistetaan nimestä ennen injektointia. set -e keskeyttää
# rakennuksen, jos jonkin version asennus epäonnistuu.
RUN set -e; \
    while read -r line || [ -n "$line" ]; do \
    # Poistetaan Windows-rivinvaihdot, kommentit ja tyhjä tila
    spec=$(echo "$line" | tr -d '\r' | sed 's/#.*//' | xargs); \
    [ -z "$spec" ] && continue; \
    name=${spec%%==*}; \
    pipx install "$spec"; \
    pipx inject "$name" ${DATASET_LIBS}; \
    done < static_analyzers.txt

# Pyright tarvitsee Node.js:n. Lukitaan Node.js-versio asentamalla se Pyrightin
# ympäristöön nodejs-wheel-binaries-pakettina; muuten Pyright lataisi uusimman
# Node.js-version ensimmäisellä ajokerralla. Pyright itse sisältyy PyPI-pakettiin.
RUN pipx inject pyright nodejs-wheel-binaries==24.19.0 && pyright --version

# Tallennetaan asennetut versiot ja kunkin työkalun riippuvuudet (esim. PythonTA:n
# ja Prospectorin sisäiset Pylint-, Mypy- ja pycodestyle-versiot) toistettavuutta varten.
# Tiedostot ovat kansiossa /opt/versions, koska /workspace/logs liitetään ajossa isäntäkoneelta.
RUN mkdir -p /opt/versions && \
    python3 --version > /opt/versions/python_version.txt && \
    pipx list --short > /opt/versions/tool_versions.txt && \
    for venv in $(pipx list --short | cut -d' ' -f1); do \
    echo "== $venv"; pipx runpip "$venv" freeze; \
    done > /opt/versions/tool_freeze.txt

# Luodaan hakemisto testiaineistoille.
RUN mkdir -p /opt/datasets

# Aineistot lukittu committeihin (HEAD 27.9.2026), jotta testitapaukset pysyvät samoina.
# Kloonataan QuixBugs-aineisto.
RUN git clone https://github.com/jkoppel/QuixBugs.git /opt/datasets/QuixBugs/ && \
    git -C /opt/datasets/QuixBugs checkout 4257f44b0ff1181dedaedee6a447e133219fcebf

# Kloonataan CODEVAIOLATION-aineisto (PEP 8 -rikkomukset ja hyvien ohjelmointikäytäntöjen rikkomukset).
RUN git clone https://github.com/CodingWithLLMs/CODEVAIOLATION.git /opt/datasets/CODEVAIOLATION/ && \
    git -C /opt/datasets/CODEVAIOLATION checkout f2eca3ed8d6b128a1cc47082885e63e91e31ce0a

# Kloonataan YesWeHack-tietoturva-aineisto.
RUN git clone https://github.com/yeswehack/vulnerable-code-snippets.git /opt/datasets/yeswehack/ && \
    git -C /opt/datasets/yeswehack checkout 90c910e15b9fd2ce7dbc06c7594a050d486b80e8

# Kopioidaan analyysiskripti konttikuvaan.
COPY tools/ /workspace/tools/

# Asetetaan tools-hakemiston Python-skriptit suoritettaviksi.
RUN chmod +x /workspace/tools/*.py

# Käynnistetään komentotulkki.
CMD ["/bin/bash"]