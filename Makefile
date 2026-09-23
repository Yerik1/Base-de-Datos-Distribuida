COMPOSE := docker compose --profile lab1

.PHONY: lab1-up lab1-down lab1-down-v lab1-status lab1-shell lab1-logs lab1-license

lab1-up:
	$(COMPOSE) up -d crdb-1 crdb-2 crdb-3
	$(COMPOSE) run --rm --no-deps crdb-init
	$(COMPOSE) build app-crdb

lab1-status:
	docker exec ti4601-crdb-1 cockroach node status --insecure --host=crdb-1:26257

lab1-shell:
	$(COMPOSE) run --rm --no-deps app-crdb bash

lab1-license:
	$(COMPOSE) run --rm --no-deps app-crdb python3 labs/lab1-cluster/install_license.py

lab1-logs:
	$(COMPOSE) logs -f crdb-1 crdb-2 crdb-3

lab1-down:
	$(COMPOSE) down

lab1-down-v:
	$(COMPOSE) down -v
