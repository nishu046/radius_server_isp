PY := ./venv/bin/python
TW := ./bin/tailwindcss
TW_VERSION := v4.3.3

.PHONY: help css css-watch run test check migrate lint tailwind-install

help:
	@grep -E '^[a-z-]+:.*?## .*$$' $(MAKEFILE_LIST) \
		| awk 'BEGIN {FS = ":.*?## "}; {printf "  %-16s %s\n", $$1, $$2}'

tailwind-install:  ## download the standalone Tailwind binary
	@mkdir -p bin
	curl -sL -o $(TW) \
		"https://github.com/tailwindlabs/tailwindcss/releases/download/$(TW_VERSION)/tailwindcss-macos-arm64"
	@chmod +x $(TW)

css:  ## build the stylesheet (minified)
	$(TW) -i static/src/input.css -o static/dist/app.css --minify

css-watch:  ## rebuild the stylesheet on change
	$(TW) -i static/src/input.css -o static/dist/app.css --watch

run: css  ## build css and start the dev server
	$(PY) manage.py runserver

test:  ## run the test suite with warnings as errors
	$(PY) -W error::UserWarning manage.py test

check:  ## django system checks, dev and production
	$(PY) manage.py check
	DJANGO_SETTINGS_MODULE=isp_management.settings.prod \
		ALLOWED_HOSTS=example.com $(PY) manage.py check --deploy

migrate:  ## apply migrations
	$(PY) manage.py migrate
