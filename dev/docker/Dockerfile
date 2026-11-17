# The images of the Makefile, so that trying the editor and its documentation needs only Docker:
#   docs-tools  MkDocs with its plugins (make docs-serve mounts the repository into it)
#   docs-site   the built documentation site (make docs-build: docker build --target docs-site --output site)
#   demo        the editor on the example router.yaml with a made-up home, served by a small web server
#               (make demo); nothing is saved and nothing reaches a real Home Assistant.
# The demo is the last stage, so a plain `docker build` makes it.

FROM python:3.14-slim AS docs-tools
COPY requirements_docs.txt /tmp/requirements_docs.txt
RUN pip install --no-cache-dir -r /tmp/requirements_docs.txt
ENV NO_MKDOCS_2_WARNING=1
WORKDIR /src

FROM docs-tools AS docs
COPY mkdocs.yml GUIDE.md PRZEWODNIK.md CHANGELOG.md ./
COPY docs docs
COPY dev/docs_site.py dev/docs_site.py
RUN mkdocs build --strict --site-dir /site

FROM scratch AS docs-site
COPY --from=docs /site /

FROM python:3.14-alpine AS demo
WORKDIR /demo
COPY custom_components/assist_router/www custom_components/assist_router/www
COPY dev/editor-demo.html dev/demo-home.js dev/
COPY tests/js/mock-editor.js tests/js/
COPY router.example.yaml router.example.pl.yaml ./
EXPOSE 8767
ENTRYPOINT ["sh", "-c", "echo '==> http://127.0.0.1:8767/dev/editor-demo.html  (English: ?lang=en; Ctrl+C stops)' && exec python3 -m http.server 8767 --bind 0.0.0.0"]
